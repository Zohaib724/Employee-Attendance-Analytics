"""Employee Attendance & Analytics API (FastAPI + MongoDB)."""
import os, re, calendar
from datetime import datetime, date, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Path
from pydantic import BaseModel, Field, ConfigDict, StrictInt, field_validator, model_validator
from pymongo import MongoClient, ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError
from bson import ObjectId

load_dotenv()
client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"), serverSelectionTimeoutMS=3000)
db = client[os.getenv("MONGO_DB", "attendance_db")]
IST = timezone(timedelta(hours=5, minutes=30))
UTC = timezone.utc
PRESENCE = {"PRESENT", "WFH", "ON_DUTY"}
STATUSES = PRESENCE | {"ABSENT", "LEAVE"}
app = FastAPI(title="Employee Attendance & Analytics API", version="2.0.0")


def now_utc(): return datetime.now(UTC).replace(microsecond=0)
def to_dt(ms):
    if isinstance(ms, bool) or not isinstance(ms, int) or not 100_000_000_000 <= ms <= 4_102_444_800_000:
        raise HTTPException(422, "timestamp must be epoch milliseconds as an integer")
    return datetime.fromtimestamp(ms // 1000, UTC)
def from_dt(value):
    if value is None: return None
    if value.tzinfo is None: value = value.replace(tzinfo=UTC)
    return int(value.timestamp()) * 1000
def as_utc(value): return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value
def truncate_second(value):
    value = as_utc(value)
    return value.replace(microsecond=0) if value is not None else None
def api_doc(doc):
    if not doc: return doc
    doc = dict(doc); doc.pop("_id", None)
    for key in ("created_at", "punch_in", "punch_out"):
        if key in doc: doc[key] = from_dt(as_utc(doc[key]))
    history=[]
    for entry in doc.get("history", []) or []:
        e=dict(entry); e["at"] = from_dt(as_utc(e.get("at")))
        changes={}
        for k,v in (e.get("changes") or {}).items():
            v=dict(v)
            if k in ("punch_in", "punch_out"):
                v={side: from_dt(as_utc(val)) for side,val in v.items()}
            changes[k]=v
        e["changes"]=changes; history.append(e)
    if "history" in doc or "emp_code" in doc and "date" in doc: doc["history"]=history
    return doc
def round_half(value, places=2):
    if value is None: return None
    return float(Decimal(str(value)).quantize(Decimal("1." + "0"*places), rounding=ROUND_HALF_UP))
def date_parse(s):
    try:
        d=date.fromisoformat(s)
        if d.isoformat()!=s: raise ValueError()
        return d
    except Exception: raise HTTPException(422, "date must be YYYY-MM-DD")
def month_bounds(month):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month or ""): raise HTTPException(422, "month must be YYYY-MM")
    y,m=map(int,month.split("-")); return date(y,m,1), date(y+1,1,1) if m==12 else date(y,m+1,1)
def working_days(start, end):
    if end <= start: return 0
    return sum(1 for i in range((end-start).days) if (start+timedelta(days=i)).weekday()<5)
def shift_start_dt(day, value):
    h,m=map(int,value.split(":")); return datetime.combine(day,time(h,m),IST)
def shift_end_dt(day, start_s, end_s):
    h,m=map(int,end_s.split(":")); result=datetime.combine(day,time(h,m),IST)
    sh,sm=map(int,start_s.split(":"))
    if (h,m) <= (sh,sm): result += timedelta(days=1)
    return result
def attendance_day(punch, emp):
    local=as_utc(punch).astimezone(IST); d=local.date()
    if emp["shift_end"] <= emp["shift_start"]:
        eh,em=map(int,emp["shift_end"].split(":"))
        if (local.hour,local.minute) < (eh,em): d -= timedelta(days=1)
    return d.isoformat()
def late_minutes(punch, shift_start, record_date):
    d=date_parse(record_date); start=shift_start_dt(d,shift_start).astimezone(UTC)
    delta=(as_utc(punch)-start).total_seconds()
    return int(delta//60) if delta > 600 else 0
def work_hours(punch_in,punch_out):
    punch_in, punch_out = truncate_second(punch_in), truncate_second(punch_out)
    return round_half((punch_out-punch_in).total_seconds()/3600,2)
def overtime(punch_out, emp, record_date):
    end=shift_end_dt(date_parse(record_date),emp["shift_start"],emp["shift_end"]).astimezone(UTC)
    mins=int((as_utc(punch_out)-end).total_seconds()//60)
    return mins if mins >= 30 else 0
def derived(doc, emp):
    pi=truncate_second(doc.get("punch_in")); po=truncate_second(doc.get("punch_out")); status=doc.get("status")
    doc["punch_in"], doc["punch_out"] = pi, po
    if status not in PRESENCE:
        doc.update(punch_in=None,punch_out=None,work_hours=None,late_minutes=0,overtime_minutes=0,half_day=False)
    else:
        doc["late_minutes"] = late_minutes(pi,emp["shift_start"],doc["date"]) if pi else 0
        doc["work_hours"] = work_hours(pi,po) if pi and po else None
        doc["overtime_minutes"] = overtime(po,emp,doc["date"]) if pi and po else 0
        doc["half_day"] = bool(doc["work_hours"] is not None and doc["work_hours"] < 4.50)
    return doc
def clean_query_date(value, name):
    if value is not None: date_parse(value)
    return value
def validate_pagination(page,page_size):
    if page < 1 or page_size < 1 or page_size > 100: raise HTTPException(422,"page must be >=1 and page_size must be 1..100")
def indexes():
    db.employees.create_index([("emp_code",ASCENDING)], unique=True, name="uq_emp_code")
    db.employees.create_index([("department",ASCENDING),("emp_code",ASCENDING)],name="department_emp")
    db.employees.create_index([("department",ASCENDING),("joined_on",ASCENDING)],name="department_joined")
    db.employees.create_index([("joined_on",ASCENDING)],name="employee_joined_on")
    db.attendance_logs.create_index([("emp_code",ASCENDING),("date",ASCENDING)],unique=True,name="uq_attendance_emp_date")
    db.attendance_logs.create_index([("date",DESCENDING),("emp_code",ASCENDING)],name="attendance_date_emp")
    db.attendance_logs.create_index([("emp_code",ASCENDING),("date",ASCENDING),("status",ASCENDING)],name="attendance_emp_date_status")
    db.attendance_logs.create_index([("emp_code",ASCENDING),("punch_in",DESCENDING)],name="attendance_emp_punch_in")
    db.attendance_logs.create_index([("date",ASCENDING),("status",ASCENDING)],name="attendance_date_status")
@app.on_event("startup")
def startup():
    # Fail fast rather than silently starting without required indexes.
    indexes()

class EmployeeIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    emp_code:str=Field(pattern=r"^EMP\d{4,6}$")
    name:str=Field(min_length=1,max_length=100)
    email:str=Field(max_length=120,pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    department:str=Field(min_length=1,max_length=50)
    shift_start:str=Field(default="09:30",pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    shift_end:str=Field(default="18:30",pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    joined_on:str
    @field_validator("joined_on")
    @classmethod
    def valid_joined(cls,v): date_parse(v); return v
    @model_validator(mode="after")
    def shift_diff(self):
        if self.shift_start==self.shift_end: raise ValueError("shift_start must differ from shift_end")
        return self
class PunchInIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    emp_code:str
    punched_at:Optional[StrictInt]=None
    status:Literal["PRESENT","WFH","ON_DUTY"]="PRESENT"
    @model_validator(mode="before")
    @classmethod
    def reject_null_timestamp(cls, value):
        if isinstance(value, dict) and "punched_at" in value and value["punched_at"] is None:
            raise ValueError("punched_at must be an integer epoch-millisecond value when supplied")
        return value
    @field_validator("punched_at")
    @classmethod
    def valid_ts(cls,v):
        if v is not None: to_dt(v)
        return v
class PunchOutIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    emp_code:str
    punched_at:Optional[StrictInt]=None
    @model_validator(mode="before")
    @classmethod
    def reject_null_timestamp(cls, value):
        if isinstance(value, dict) and "punched_at" in value and value["punched_at"] is None:
            raise ValueError("punched_at must be an integer epoch-millisecond value when supplied")
        return value
    @field_validator("punched_at")
    @classmethod
    def valid_ts(cls,v):
        if v is not None: to_dt(v)
        return v
class RegularizeIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    status:Optional[Literal["PRESENT","WFH","ON_DUTY","ABSENT","LEAVE"]]=None
    punch_in:Optional[StrictInt]=None
    punch_out:Optional[StrictInt]=None
    reason:str=Field(min_length=5,max_length=200)
    regularized_by:str=Field(min_length=1,max_length=50)
    @model_validator(mode="before")
    @classmethod
    def reject_null_timestamps(cls, value):
        if isinstance(value, dict):
            if any(k in value and value[k] is None for k in ("punch_in", "punch_out")):
                raise ValueError("punch timestamps must be integer epoch-millisecond values when supplied; omit to leave unchanged")
            if "status" in value and value["status"] is None:
                raise ValueError("status must be omitted or a valid status value")
        return value
    @field_validator("punch_in","punch_out")
    @classmethod
    def valid_ts(cls,v):
        if v is not None: to_dt(v)
        return v

@app.get("/health")
def health():
    try: client.admin.command("ping"); return {"status":"ok"}
    except Exception: raise HTTPException(503,"MongoDB unavailable")
@app.post("/employees",status_code=201)
def create_employee(body:EmployeeIn):
    doc=body.model_dump(); doc["created_at"]=now_utc()
    try: db.employees.insert_one(doc)
    except DuplicateKeyError: raise HTTPException(409,"emp_code already exists")
    return api_doc(doc)
@app.get("/employees")
def list_employees(department:Optional[str]=None,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100)):
    q={"department":department} if department is not None else {}
    return {"items":[api_doc(x) for x in db.employees.find(q,{"_id":0}).sort("emp_code",ASCENDING).skip((page-1)*page_size).limit(page_size)],"total":db.employees.count_documents(q),"page":page,"page_size":page_size}
@app.post("/attendance/punch-in",status_code=201)
def punch_in(body:PunchInIn):
    emp=db.employees.find_one({"emp_code":body.emp_code})
    if not emp: raise HTTPException(404,"unknown employee")
    ts=to_dt(body.punched_at) if body.punched_at is not None else now_utc(); d=attendance_day(ts,emp)
    doc={"emp_code":body.emp_code,"date":d,"status":body.status,"punch_in":ts,"punch_out":None,"work_hours":None,"late_minutes":late_minutes(ts,emp["shift_start"],d),"overtime_minutes":0,"half_day":False,"history":[]}
    try: db.attendance_logs.insert_one(doc)
    except DuplicateKeyError: raise HTTPException(409,"already punched in for this date")
    return api_doc(doc)

def attendance_filter(emp_code=None,date_from=None,date_to=None,status=None):
    q={}
    if emp_code is not None: q["emp_code"]=emp_code
    if date_from or date_to:
        q["date"]={}
        if date_from:q["date"]["$gte"]=date_from
        if date_to:q["date"]["$lte"]=date_to
    if status is not None:q["status"]=status
    return q
@app.get("/attendance")
def list_attendance(emp_code:Optional[str]=None,date_from:Optional[str]=None,date_to:Optional[str]=None,status:Optional[Literal["PRESENT","ABSENT","LEAVE","WFH","ON_DUTY"]]=None,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100)):
    for v in (date_from,date_to): clean_query_date(v,"date")
    if date_from and date_to and date_from>date_to: raise HTTPException(422,"date_from must be <= date_to")
    if status is not None and status not in STATUSES: raise HTTPException(422,"invalid status")
    q=attendance_filter(emp_code,date_from,date_to,status)
    docs=db.attendance_logs.find(q,{"_id":0}).sort([("date",DESCENDING),("emp_code",ASCENDING)]).skip((page-1)*page_size).limit(page_size)
    return {"items":[api_doc(x) for x in docs],"total":db.attendance_logs.count_documents(q),"page":page,"page_size":page_size}
@app.post("/attendance/punch-out")
def punch_out(body:PunchOutIn):
    emp=db.employees.find_one({"emp_code":body.emp_code})
    if not emp: raise HTTPException(404,"unknown employee")
    ts=to_dt(body.punched_at) if body.punched_at is not None else now_utc()
    rec=db.attendance_logs.find_one({"emp_code":body.emp_code,"punch_in":{"$ne":None,"$lte":ts}},sort=[("punch_in",DESCENDING)])
    if not rec: raise HTTPException(404,"no punch-in found")
    pi=truncate_second(rec.get("punch_in"))
    if ts<=pi or ts-pi>timedelta(hours=24): raise HTTPException(422,"punch_out must be after punch_in and within 24 hours")
    update={"punch_in":pi,"punch_out":ts,"work_hours":work_hours(pi,ts),"overtime_minutes":overtime(ts,emp,rec["date"]),"half_day":work_hours(pi,ts)<4.5}
    result=db.attendance_logs.update_one({"_id":rec["_id"],"punch_out":None},{"$set":update})
    if result.modified_count==0:
        latest=db.attendance_logs.find_one({"_id":rec["_id"]})
        if latest and latest.get("punch_out") is not None: raise HTTPException(409,"already punched out")
        raise HTTPException(409,"record changed concurrently")
    rec.update(update); return api_doc(rec)
@app.patch("/attendance/{emp_code}/{date}")
def regularize(emp_code:str,date:str,body:RegularizeIn):
    date_parse(date); emp=db.employees.find_one({"emp_code":emp_code})
    if not emp: raise HTTPException(404,"unknown employee")
    rec=db.attendance_logs.find_one({"emp_code":emp_code,"date":date})
    if not rec: raise HTTPException(404,"attendance record not found")
    fields=body.model_dump(exclude={"reason","regularized_by"},exclude_unset=True)
    old=dict(rec); new=dict(rec)
    # MongoClient returns naive UTC datetimes by default; normalize existing values
    # before comparing them with the aware UTC instants parsed from the request.
    for field in ("punch_in", "punch_out"):
        new[field] = as_utc(new.get(field))
    if "status" in fields:new["status"]=fields["status"]
    if new.get("status") in ("ABSENT", "LEAVE") and any(f in fields and fields[f] is not None for f in ("punch_in", "punch_out")):
        raise HTTPException(422,"ABSENT/LEAVE cannot have punch times")
    for f in ("punch_in","punch_out"):
        if f in fields:new[f]=to_dt(fields[f]) if fields[f] is not None else None
    if new["status"] in PRESENCE and new.get("punch_in") is None: raise HTTPException(422,"presence status requires punch_in")
    if new.get("punch_in") is not None and attendance_day(new["punch_in"],emp)!=date: raise HTTPException(422,"punch_in must belong to attendance date")
    if new.get("punch_out") is not None:
        if new.get("punch_in") is None or new["punch_out"]<=new["punch_in"] or new["punch_out"]-new["punch_in"]>timedelta(hours=24): raise HTTPException(422,"invalid punch_out")
    new=derived(new,emp)
    change_keys=["status","punch_in","punch_out","work_hours","late_minutes","overtime_minutes","half_day"]
    defaults={"punch_in":None,"punch_out":None,"work_hours":None,"late_minutes":0,"overtime_minutes":0,"half_day":False}
    changes={}
    for k in change_keys:
        a=old.get(k, defaults.get(k)); b=new.get(k, defaults.get(k))
        if k in ("punch_in","punch_out"): a=as_utc(a); b=as_utc(b)
        if a!=b: changes[k]={"from":a,"to":b}
    if not changes: raise HTTPException(422,"request does not change the record")
    entry={"at":now_utc(),"by":body.regularized_by,"reason":body.reason,"changes":changes}
    # Atomic compare-and-set prevents concurrent edits from overwriting history.
    old_history=rec.get("history",[]) or []
    query={"_id":rec["_id"]}
    if "history" in rec:
        query["history"]=old_history
    else:
        query["history"]={"$exists":False}
    for k in change_keys:
        if k in rec: query[k]=rec[k]
        else: query[k]={"$exists":False}
    new["history"]=old_history+[entry]
    sets={k:new.get(k) for k in change_keys}; sets["history"]=new["history"]
    result=db.attendance_logs.update_one(query,{"$set":sets})
    if not result.modified_count: raise HTTPException(409,"record changed concurrently; retry")
    return api_doc(new)

def employee_monthly_pipeline(emp_code: str, start: date, end: date):
    weekday = {"$lt": [{"$isoDayOfWeek": {"$dateFromString": {"dateString": "$date"}}}, 6]}
    return [
        {"$match": {"emp_code": emp_code, "date": {"$gte": start.isoformat(), "$lt": end.isoformat()}}},
        {"$group": {
            "_id": "$emp_code",
            "present_days": {"$sum": {"$cond": [
                {"$and": [{"$in": ["$status", list(PRESENCE)]}, weekday]},
                {"$cond": [{"$eq": [{"$ifNull": ["$half_day", False]}, True]}, 0.5, 1]},
                0,
            ]}},
            "leave_days": {"$sum": {"$cond": [{"$eq": ["$status", "LEAVE"]}, 1, 0]}},
            "late_count": {"$sum": {"$cond": [{"$gt": [{"$ifNull": ["$late_minutes", 0]}, 0]}, 1, 0]}},
            "total_late_minutes": {"$sum": {"$ifNull": ["$late_minutes", 0]}},
            "total_overtime_minutes": {"$sum": {"$ifNull": ["$overtime_minutes", 0]}},
        }},
    ]


def department_summary_pipeline(start: date, end: date, department: Optional[str] = None):
    month_start = start.isoformat()
    emp_match = {"joined_on": {"$lte": (end - timedelta(days=1)).isoformat()}}
    if department is not None:
        emp_match["department"] = department
    weekday = {"$lt": [{"$isoDayOfWeek": {"$dateFromString": {"dateString": "$date"}}}, 6]}
    present_status = {"$in": ["$status", list(PRESENCE)]}
    completed_present = {"$and": [present_status, {"$ne": [{"$ifNull": ["$work_hours", None]}, None]}]}
    return [
        {"$match": emp_match},
        {"$group": {"_id": "$department", "headcount": {"$sum": 1}, "codes": {"$push": "$emp_code"}}},
        {"$lookup": {
            "from": "attendance_logs",
            "let": {"codes": "$codes"},
            "pipeline": [
                {"$match": {"date": {"$gte": month_start, "$lt": end.isoformat()}, "$expr": {"$in": ["$emp_code", "$$codes"]}}},
                {"$group": {
                    "_id": None,
                    "present_days": {"$sum": {"$cond": [
                        {"$and": [present_status, weekday]},
                        {"$cond": [{"$eq": [{"$ifNull": ["$half_day", False]}, True]}, 0.5, 1]},
                        0,
                    ]}},
                    # This is a record-weighted mean, not a mean of employee means.
                    "avg_work_hours": {"$avg": {"$cond": [completed_present, "$work_hours", None]}},
                    "late_count": {"$sum": {"$cond": [{"$gt": [{"$ifNull": ["$late_minutes", 0]}, 0]}, 1, 0]}},
                    "total_late_minutes": {"$sum": {"$ifNull": ["$late_minutes", 0]}},
                    "leave_count": {"$sum": {"$cond": [{"$eq": ["$status", "LEAVE"]}, 1, 0]}},
                    "on_duty_count": {"$sum": {"$cond": [{"$eq": ["$status", "ON_DUTY"]}, 1, 0]}},
                }},
            ],
            "as": "stats",
        }},
        {"$set": {"s": {"$ifNull": [
            {"$arrayElemAt": ["$stats", 0]},
            {"present_days": 0, "avg_work_hours": None, "late_count": 0, "total_late_minutes": 0, "leave_count": 0, "on_duty_count": 0},
        ]}}},
        {"$project": {
            "_id": 0, "department": "$_id", "headcount": 1,
            "present_days": "$s.present_days", "avg_work_hours": "$s.avg_work_hours",
            "late_count": "$s.late_count", "total_late_minutes": "$s.total_late_minutes",
            "leave_count": "$s.leave_count", "on_duty_count": "$s.on_duty_count",
        }},
        {"$sort": {"department": 1}},
    ]


def late_leaderboard_pipeline(start: date, end: date, limit: int, department: Optional[str] = None):
    pipeline = [
        {"$match": {"date": {"$gte": start.isoformat(), "$lt": end.isoformat()}, "late_minutes": {"$gt": 0}}},
        {"$group": {"_id": "$emp_code", "total_late_minutes": {"$sum": "$late_minutes"}, "late_count": {"$sum": 1}}},
        {"$lookup": {"from": "employees", "localField": "_id", "foreignField": "emp_code", "as": "emp"}},
        {"$unwind": "$emp"},
    ]
    if department is not None:
        pipeline.append({"$match": {"emp.department": department}})
    pipeline.extend([
        {"$setWindowFields": {"sortBy": {"total_late_minutes": -1}, "output": {"rank": {"$rank": {}}}}},
        {"$match": {"rank": {"$lte": limit}}},
        {"$sort": {"total_late_minutes": -1, "_id": 1}},
        {"$project": {"_id": 0, "emp_code": "$_id", "name": "$emp.name", "department": "$emp.department", "total_late_minutes": 1, "late_count": 1, "rank": 1}},
    ])
    return pipeline


def half_up_4(value):
    # MongoDB $round uses ties-to-even; R8 requires half-up for non-negative rates.
    return {"$divide": [{"$floor": {"$add": [{"$multiply": [value, 10000]}, 0.5]}}, 10000]}


def department_trend_pipeline(department: str, from_date: str, to_date: str):
    start = date_parse(from_date)
    end = date_parse(to_date)
    if end < start:
        raise HTTPException(422, "to must be >= from")
    days = (end - start).days + 1
    if days > 92:
        raise HTTPException(422, "range cannot exceed 92 days")

    # Start from one anchor employee so a calendar spine exists even before the
    # department's first join date. The analytics themselves stay in MongoDB.
    raw_rate = {"$divide": ["$present_count", "$headcount"]}
    pipeline = [
        {"$match": {"department": department}},
        {"$limit": 1},
        {"$project": {"_id": 0, "days": {"$map": {
            "input": {"$range": [0, days]}, "as": "offset",
            "in": {"$dateToString": {"date": {"$dateAdd": {
                "startDate": {"$dateFromString": {"dateString": from_date}},
                "unit": "day", "amount": "$$offset",
            }}, "format": "%Y-%m-%d", "timezone": "+00:00"}},
        }}}},
        {"$unwind": "$days"},
        {"$lookup": {
            "from": "employees", "let": {"day": "$days"},
            "pipeline": [{"$match": {"department": department, "$expr": {"$lte": ["$joined_on", "$$day"]}}}, {"$project": {"_id": 0, "emp_code": 1}}],
            "as": "eligible_employees",
        }},
        {"$set": {
            "date": "$days",
            "headcount": {"$size": "$eligible_employees"},
            "codes": {"$map": {"input": "$eligible_employees", "as": "employee", "in": "$$employee.emp_code"}},
            "dayDate": {"$dateFromString": {"dateString": "$days"}},
        }},
        {"$lookup": {
            "from": "attendance_logs", "let": {"day": "$days", "codes": "$codes"},
            "pipeline": [{"$match": {"$expr": {"$and": [
                {"$eq": ["$date", "$$day"]},
                {"$in": ["$emp_code", "$$codes"]},
            ]}}}],
            "as": "logs",
        }},
        {"$set": {
            "present_count": {"$reduce": {"input": "$logs", "initialValue": 0, "in": {"$add": ["$$value", {"$cond": [
                {"$in": ["$$this.status", list(PRESENCE)]},
                {"$cond": [{"$eq": [{"$ifNull": ["$$this.half_day", False]}, True]}, 0.5, 1]},
                0,
            ]}]}}},
            "late_count": {"$reduce": {"input": "$logs", "initialValue": 0, "in": {"$add": ["$$value", {"$cond": [
                {"$gt": [{"$ifNull": ["$$this.late_minutes", 0]}, 0]}, 1, 0,
            ]}]}}},
            "is_working_day": {"$lt": [{"$isoDayOfWeek": "$dayDate"}, 6]},
        }},
        {"$set": {"attendance_rate": {"$cond": [
            {"$and": ["$is_working_day", {"$gt": ["$headcount", 0]}]},
            half_up_4(raw_rate),
            None,
        ]}}},
        {"$setWindowFields": {"sortBy": {"dayDate": 1}, "output": {
            "_moving_raw": {"$avg": "$attendance_rate", "window": {"documents": [-6, 0]},
        }}}},
        {"$set": {"moving_avg_7d": {"$cond": [
            {"$ne": ["$_moving_raw", None]}, half_up_4("$_moving_raw"), None,
        ]}}},
        {"$project": {"_id": 0, "date": 1, "is_working_day": 1, "headcount": 1, "present_count": 1, "late_count": 1, "attendance_rate": 1, "moving_avg_7d": 1}},
        {"$sort": {"date": 1}},
    ]
    return pipeline


@app.get("/analytics/employees/{emp_code}/monthly")
def employee_monthly(emp_code: str, month: str):
    start, end = month_bounds(month)
    emp = db.employees.find_one({"emp_code": emp_code})
    if not emp:
        raise HTTPException(404, "unknown employee")
    first = max(start, date_parse(emp["joined_on"]))
    working = working_days(first, end)
    row = next(iter(db.attendance_logs.aggregate(employee_monthly_pipeline(emp_code, start, end))), {})
    present = round_half(row.get("present_days", 0))
    pct = round_half(present / working * 100, 4) if working else None
    return {"emp_code": emp_code, "month": month, "working_days": working, "present_days": present,
            "leave_days": row.get("leave_days", 0), "late_count": row.get("late_count", 0),
            "total_late_minutes": row.get("total_late_minutes", 0),
            "total_overtime_minutes": row.get("total_overtime_minutes", 0), "attendance_pct": pct}


@app.get("/analytics/departments/summary")
def department_summary(month: str, department: Optional[str] = None):
    start, end = month_bounds(month)
    rows = list(db.employees.aggregate(department_summary_pipeline(start, end, department)))
    for row in rows:
        row["present_days"] = round_half(row.get("present_days", 0))
        row["avg_work_hours"] = round_half(row.get("avg_work_hours"))
    return {"month": month, "items": rows}


@app.get("/analytics/leaderboard/late")
def late_leaderboard(month: str, limit: int = Query(10, ge=1, le=50), department: Optional[str] = None):
    start, end = month_bounds(month)
    return {"month": month, "items": list(db.attendance_logs.aggregate(late_leaderboard_pipeline(start, end, limit, department)))}


@app.get("/analytics/departments/{department}/trend")
def department_trend(department: str, from_date: str = Query(alias="from"), to_date: str = Query(alias="to")):
    start = date_parse(from_date)
    end = date_parse(to_date)
    if end < start:
        raise HTTPException(422, "to must be >= from")
    if (end - start).days + 1 > 92:
        raise HTTPException(422, "range cannot exceed 92 days")
    if not db.employees.find_one({"department": department}, {"_id": 1}):
        raise HTTPException(404, "unknown department")
    return {"department": department, "items": list(db.employees.aggregate(department_trend_pipeline(department, from_date, to_date), allowDiskUse=True))}


@app.get("/admin/explain/{endpoint}")
def explain(
    endpoint: str,
    emp_code: Optional[str] = None,
    month: Optional[str] = None,
    department: Optional[str] = None,
    limit: int = Query(10, ge=1, le=50),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[Literal["PRESENT", "ABSENT", "LEAVE", "WFH", "ON_DUTY"]] = None,
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    allowed = {"attendance_list", "employee_monthly", "department_summary", "late_leaderboard", "department_trend"}
    if endpoint not in allowed:
        raise HTTPException(422, "unsupported endpoint")

    if endpoint == "attendance_list":
        for value in (date_from, date_to):
            clean_query_date(value, "date")
        if date_from and date_to and date_from > date_to:
            raise HTTPException(422, "date_from must be <= date_to")
        if status is not None and status not in STATUSES:
            raise HTTPException(422, "invalid status")
        query = attendance_filter(emp_code, date_from, date_to, status)
        explain_doc = db.command("explain", {
            "find": "attendance_logs", "filter": query,
            "sort": {"date": -1, "emp_code": 1},
            "skip": (page - 1) * page_size, "limit": page_size,
        }, verbosity="executionStats")
        collection = "attendance_logs"
    elif endpoint == "employee_monthly":
        if not emp_code or not month:
            raise HTTPException(422, "emp_code and month are required")
        start, end = month_bounds(month)
        pipeline = employee_monthly_pipeline(emp_code, start, end)
        explain_doc = db.command("explain", {"aggregate": "attendance_logs", "pipeline": pipeline, "cursor": {}}, verbosity="executionStats")
        collection = "attendance_logs"
    elif endpoint == "department_summary":
        if not month:
            raise HTTPException(422, "month is required")
        start, end = month_bounds(month)
        pipeline = department_summary_pipeline(start, end, department)
        explain_doc = db.command("explain", {"aggregate": "employees", "pipeline": pipeline, "cursor": {}}, verbosity="executionStats")
        collection = "employees"
    elif endpoint == "late_leaderboard":
        if not month:
            raise HTTPException(422, "month is required")
        start, end = month_bounds(month)
        pipeline = late_leaderboard_pipeline(start, end, limit, department)
        explain_doc = db.command("explain", {"aggregate": "attendance_logs", "pipeline": pipeline, "cursor": {}}, verbosity="executionStats")
        collection = "attendance_logs"
    else:
        if not department or not from_date or not to_date:
            raise HTTPException(422, "department, from and to are required")
        start = date_parse(from_date)
        end = date_parse(to_date)
        if end < start or (end - start).days + 1 > 92:
            raise HTTPException(422, "invalid trend date range")
        pipeline = department_trend_pipeline(department, from_date, to_date)
        explain_doc = db.command("explain", {"aggregate": "employees", "pipeline": pipeline, "cursor": {}}, verbosity="executionStats")
        collection = "employees"
    return {"endpoint": endpoint, "collection": collection, "explain": explain_doc}
