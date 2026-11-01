"""Validated and transactional implementations of three SQLite loading strategies."""
import csv, hashlib, json, math, time, uuid, logging, sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

_logger=logging.getLogger("data_pipeline")
if not _logger.handlers:
    _handler=logging.StreamHandler(sys.stderr);_handler.setFormatter(logging.Formatter("%(message)s"));_logger.addHandler(_handler);_logger.setLevel(logging.INFO)
def _event(event, **fields): _logger.info(json.dumps({"event":event,"timestamp":now(),**fields},default=str,sort_keys=True))

COLUMNS=["order_id","order_date","customer_id","amount","status","updated_at"]
VALID_STATUSES={"PLACED","SHIPPED","DELIVERED","CANCELLED","NEW","PAID"}
TARGETS={"full_refresh":"full_refresh_orders","incremental_merge":"incremental_orders","partition_replacement":"partition_orders"}

class InputReadError(ValueError):
    def __init__(self,message,valid,rejects,source_records,duplicates,source_positions):
        super().__init__(message);self.valid=valid;self.rejects=rejects;self.source_records=source_records;self.duplicates=duplicates;self.source_positions=source_positions

def now(): return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
def normalize_timestamp(value):
    dt=datetime.fromisoformat(value.strip().replace("Z","+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None: raise ValueError("updated_at must include a timezone offset")
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00","Z")

def _decoded_utf8_lines(binary_file):
    first=True
    for raw_line in binary_file:
        yield raw_line.decode('utf-8-sig' if first else 'utf-8')
        first=False

def read_and_validate(path,conn,run_id=None):
    valid=[]; rejects=[]; duplicates=0; seen={}; source_positions={}; source_records=0
    customers={r[0] for r in conn.execute("SELECT customer_id FROM customers")}
    with open(path,'rb') as f:
        reader=csv.DictReader(_decoded_utf8_lines(f),strict=True); headers=reader.fieldnames or []
        if len(headers)!=len(set(headers)): raise ValueError("Duplicate CSV headers are not allowed")
        if headers!=COLUMNS: raise ValueError(f"CSV header must exactly match: {','.join(COLUMNS)}")
        try:
            for raw in reader:
                source_records+=1
                try:
                    if None in raw or any(v is None for v in raw.values()): raise ValueError("record has extra or missing CSV fields")
                    oid=int(raw['order_id']); cid=int(raw['customer_id']); amount_d=Decimal(raw['amount'].strip())
                    if not amount_d.is_finite(): raise ValueError("amount must be finite")
                    if amount_d<0: raise ValueError("amount cannot be negative")
                    if amount_d.as_tuple().exponent < -2: raise ValueError("amount supports at most two decimal places")
                    if amount_d>Decimal('999999999999.99'): raise ValueError("amount exceeds supported range")
                    amount=float(amount_d)
                    od=raw['order_date'].strip(); parsed=datetime.strptime(od,'%Y-%m-%d').date()
                    if parsed.isoformat()!=od: raise ValueError("order_date must use YYYY-MM-DD")
                    ts=normalize_timestamp(raw['updated_at']); status=raw['status'].strip()
                    if oid<=0: raise ValueError("order_id must be positive")
                    if cid not in customers: raise ValueError("unknown customer_id")
                    if not math.isfinite(amount): raise ValueError("amount must be finite")
                    if status not in VALID_STATUSES: raise ValueError(f"invalid order status: {status}")
                    row=(oid,od,cid,amount,status,ts)
                    if oid in seen:
                        if seen[oid]==row: duplicates+=1; continue
                        raise ValueError("conflicting duplicate order_id in input")
                    seen[oid]=row; source_positions[oid]=source_records; valid.append(row)
                except Exception as exc:
                    rejects.append((json.dumps({str(k):v for k,v in raw.items()},sort_keys=True,default=str),str(exc),source_records))
        except (csv.Error, UnicodeDecodeError) as exc:
            if isinstance(exc,csv.Error): message=f"Malformed CSV syntax near line {reader.line_num}: {exc}"
            else: message=f"Invalid UTF-8 encoding after {source_records} source records: {exc}"
            raise InputReadError(message,valid,rejects,source_records,duplicates,source_positions) from exc
    return valid,rejects,source_records,duplicates,source_positions

def _start_run(conn,strategy,path,changed_partitions):
    run_id=str(uuid.uuid4()); p=Path(path); source_path=str(p.resolve())
    digest=hashlib.sha256(p.read_bytes()).hexdigest()
    mode="complete_snapshot" if strategy in ("full_refresh","partition_replacement") else "change_feed"
    scope=json.dumps(changed_partitions,sort_keys=True) if changed_partitions is not None else None
    conn.execute("INSERT INTO pipeline_runs(run_id,strategy,started_at,status,source_file,source_sha256,input_mode,partition_scope) VALUES (?,?,?,'RUNNING',?,?,?,?)",(run_id,strategy,now(),source_path,digest,mode,scope)); conn.commit()
    return run_id,digest

def _finish(conn,run_id,status,counts,duration,error=None,commit=True):
    conn.execute("UPDATE pipeline_runs SET ended_at=?,status=?,input_count=?,output_count=?,rejected_count=?,duration_ms=?,error_message=?,accepted_count=?,duplicate_count=?,stale_count=?,unchanged_count=?,inserted_count=?,updated_count=?,deleted_count=?,ignored_scope_count=? WHERE run_id=?",(now(),status,counts.get('source_records',0),counts.get('output_count',0),counts.get('rejected_count',0),duration,error,counts.get('accepted_count',0),counts.get('duplicate_count',0),counts.get('stale_count',0),counts.get('unchanged_count',0),counts.get('inserted_count',0),counts.get('updated_count',0),counts.get('deleted_count',0),counts.get('ignored_scope_count',0),run_id));
    if commit: conn.commit()

def _quarantine(conn,run_id,path,rejects):
    if not rejects:return
    conn.execute('BEGIN')
    for raw,reason,record_no in rejects:
        conn.execute("INSERT INTO rejects(run_id,source_file,raw_record,reason,source_record_number) VALUES (?,?,?,?,?)",(run_id,str(path),raw,reason,record_no))
    conn.commit()

def run_strategy(conn,strategy,source_file,changed_partitions=None,fail_before_commit=False):
    if strategy not in TARGETS: raise ValueError(f"Unknown strategy: {strategy}")
    target=TARGETS[strategy]; run_id,digest=_start_run(conn,strategy,source_file,changed_partitions); started=time.perf_counter(); rejects_persisted=False
    _event('run_started',run_id=run_id,strategy=strategy,source_file=str(source_file),source_sha256=digest)
    counts={k:0 for k in ['source_records','accepted_count','duplicate_count','rejected_count','stale_count','unchanged_count','inserted_count','updated_count','deleted_count','ignored_scope_count','output_count']}; rejects=[]
    try:
        try:
            valid,rejects,source_records,duplicates,source_positions=read_and_validate(source_file,conn,run_id)
        except InputReadError as read_error:
            valid,rejects=read_error.valid,read_error.rejects
            counts.update(source_records=read_error.source_records,accepted_count=len(valid),duplicate_count=read_error.duplicates,rejected_count=len(rejects))
            raise
        counts.update(source_records=source_records,accepted_count=len(valid),duplicate_count=duplicates,rejected_count=len(rejects))
        if strategy=='partition_replacement' and rejects: raise ValueError('partition replacement aborted: source contains rejected rows')
        # Commit quarantine evidence before opening the target transaction so it
        # survives any subsequent target rollback.
        _quarantine(conn,run_id,source_file,rejects); rejects_persisted=True
        conn.execute('BEGIN')
        if strategy=='full_refresh':
            previous=[tuple(r) for r in conn.execute(f'SELECT order_id,order_date,customer_id,amount,status,updated_at FROM {target}')]
            counts['deleted_count']=len(previous)
            for old_row in previous:
                conn.execute("INSERT INTO change_log(order_id,operation,changed_at,source_file,source_sha256,run_id,old_values) VALUES (?,?,?,?,?,?,?)",(old_row[0],'DELETE',now(),str(source_file),digest,run_id,json.dumps(old_row[1:])))
            conn.execute(f'DELETE FROM {target}')
            conn.executemany(f'INSERT INTO {target} VALUES (?,?,?,?,?,?)',valid); counts['inserted_count']=len(valid)
            for row in valid:
                conn.execute("INSERT INTO change_log(order_id,operation,changed_at,source_file,source_sha256,run_id,source_record_number,new_values) VALUES (?,?,?,?,?,?,?,?)",(row[0],'INSERT',now(),str(source_file),digest,run_id,source_positions.get(row[0]),json.dumps(row[1:])))
        elif strategy=='incremental_merge':
            for row in valid:
                old=conn.execute(f'SELECT order_date,customer_id,amount,status,updated_at FROM {target} WHERE order_id=?',(row[0],)).fetchone()
                if old:
                    old=tuple(old); new=tuple(row[1:])
                    if row[5]<old[4]: counts['stale_count']+=1; continue
                    if row[5]==old[4]:
                        if new==old: counts['unchanged_count']+=1; continue
                        raise ValueError(f'conflicting payload for order_id={row[0]} at equal updated_at')
                    conn.execute(f'UPDATE {target} SET order_date=?,customer_id=?,amount=?,status=?,updated_at=? WHERE order_id=?',(*row[1:],row[0])); counts['updated_count']+=1
                    conn.execute("INSERT INTO change_log(order_id,operation,changed_at,source_file,source_sha256,run_id,source_record_number,old_values,new_values) VALUES (?,?,?,?,?,?,?,?,?)",(row[0],'UPDATE',now(),str(source_file),digest,run_id,source_positions.get(row[0]),json.dumps(old),json.dumps(new)))
                else:
                    conn.execute(f'INSERT INTO {target} VALUES (?,?,?,?,?,?)',row); counts['inserted_count']+=1
                    conn.execute("INSERT INTO change_log(order_id,operation,changed_at,source_file,source_sha256,run_id,source_record_number,new_values) VALUES (?,?,?,?,?,?,?,?)",(row[0],'INSERT',now(),str(source_file),digest,run_id,source_positions.get(row[0]),json.dumps(row[1:])))
        else:
            partitions=sorted(set(changed_partitions if changed_partitions is not None else [r[1] for r in valid]))
            if any(datetime.strptime(d,'%Y-%m-%d').date().isoformat()!=d for d in partitions): raise ValueError('invalid partition date in changed_partitions')
            out_scope=[r for r in valid if r[1] not in partitions]; counts['ignored_scope_count']=len(out_scope)
            # If an existing key moves dates, both old and new partitions must be in scope.
            for row in valid:
                old=conn.execute(f'SELECT order_date FROM {target} WHERE order_id=?',(row[0],)).fetchone()
                if old and old[0]!=row[1] and (old[0] not in partitions or row[1] not in partitions):
                    raise ValueError(f'partition movement for order_id={row[0]} requires both {old[0]} and {row[1]} in changed_partitions')
            grouped={d:[] for d in partitions}
            for row in valid:
                if row[1] in grouped: grouped[row[1]].append(row)
            for d in partitions:
                previous=[tuple(r) for r in conn.execute(f'SELECT order_id,order_date,customer_id,amount,status,updated_at FROM {target} WHERE order_date=?',(d,))]
                counts['deleted_count']+=len(previous)
                for old_row in previous:
                    conn.execute("INSERT INTO change_log(order_id,operation,changed_at,source_file,source_sha256,run_id,old_values) VALUES (?,?,?,?,?,?,?)",(old_row[0],'DELETE',now(),str(source_file),digest,run_id,json.dumps(old_row[1:])))
                conn.execute(f'DELETE FROM {target} WHERE order_date=?',(d,))
                conn.executemany(f'INSERT INTO {target} VALUES (?,?,?,?,?,?)',grouped[d]); counts['inserted_count']+=len(grouped[d])
                for row in grouped[d]:
                    conn.execute("INSERT INTO change_log(order_id,operation,changed_at,source_file,source_sha256,run_id,source_record_number,new_values) VALUES (?,?,?,?,?,?,?,?)",(row[0],'INSERT',now(),str(source_file),digest,run_id,source_positions.get(row[0]),json.dumps(row[1:])))
        if fail_before_commit: raise RuntimeError('Simulated failure before commit')
        counts['output_count']=conn.execute(f'SELECT COUNT(*) FROM {target}').fetchone()[0]
        duration=(time.perf_counter()-started)*1000
        _finish(conn,run_id,'SUCCESS',counts,duration,commit=False)
        conn.commit()  # target publication and terminal SUCCESS state are atomic
        _event('run_succeeded',run_id=run_id,strategy=strategy,counts=counts,duration_ms=round(duration,3))
        return {'run_id':run_id,'strategy':strategy,'status':'SUCCESS','input_count':counts['source_records'],**counts,'duration_ms':round(duration,3),'source_sha256':digest}
    except Exception as exc:
        conn.rollback()
        if not rejects_persisted:
            try:_quarantine(conn,run_id,source_file,rejects)
            except Exception:conn.rollback()
        counts['output_count']=conn.execute(f'SELECT COUNT(*) FROM {target}').fetchone()[0]
        duration=(time.perf_counter()-started)*1000
        try:_finish(conn,run_id,'FAILED',counts,duration,str(exc))
        except Exception:conn.rollback()
        _event('run_failed',run_id=run_id,strategy=strategy,failure_stage='validation_or_target_transaction',error=str(exc),counts=counts)
        return {'run_id':run_id,'strategy':strategy,'status':'FAILED','input_count':counts['source_records'],**counts,'duration_ms':round(duration,3),'error':str(exc)}

def snapshot(conn,table):
    if table not in set(TARGETS.values()): raise ValueError('Unknown target table')
    return [tuple(r) for r in conn.execute(f'SELECT order_id,order_date,customer_id,amount,status,updated_at FROM {table} ORDER BY order_id')]
