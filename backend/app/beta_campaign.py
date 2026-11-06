"""Fixed-budget beta cohort. Earned bonus is not a bank transfer or spendable credit."""
import json
import secrets
from datetime import timedelta
from . import rewards

CAMPAIGN = 'beta30-20261106'
CAPACITY, RECEIPTS, DAYS, PER_RECEIPT, BONUS = 15, 42, 14, 300, 5000
COMPLETION_RECEIPTS = 3
RESERVED_KRW = BONUS + RECEIPTS * PER_RECEIPT


def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS beta_members (
      campaign TEXT NOT NULL, uid TEXT NOT NULL, starts_at TEXT NOT NULL,
      ends_at TEXT NOT NULL, survey TEXT, survey_at TEXT,
      PRIMARY KEY(campaign,uid));
    CREATE TABLE IF NOT EXISTS beta_applications (
      campaign TEXT NOT NULL, uid TEXT NOT NULL, created_at TEXT NOT NULL,
      PRIMARY KEY(campaign,uid));
    CREATE TABLE IF NOT EXISTS beta_receipts (
      receipt_id TEXT PRIMARY KEY REFERENCES receipts(id),
      campaign TEXT NOT NULL, uid TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS beta_awards (
      campaign TEXT NOT NULL, uid TEXT NOT NULL, created_at TEXT NOT NULL,
      PRIMARY KEY(campaign,uid));
    CREATE TABLE IF NOT EXISTS beta_payouts (
      id TEXT PRIMARY KEY, uid TEXT NOT NULL, request_id TEXT NOT NULL,
      receipt_id TEXT, amount_krw INTEGER NOT NULL CHECK(amount_krw=5000),
      recipient_encrypted TEXT NOT NULL, account_tail TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending', reference TEXT UNIQUE,
      reason TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      UNIQUE(uid,request_id));
    CREATE UNIQUE INDEX IF NOT EXISTS beta_payout_active ON beta_payouts(uid)
      WHERE status IN ('pending','processing','paid');
    ''')


def enroll(store, uid, actor):
    if not uid.startswith('kakao_'):
        raise ValueError('linked_account_required')
    with rewards._LOCK, store._db() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM beta_members WHERE campaign=? AND uid=?', (CAMPAIGN,uid)).fetchone()
        if not row:
            if db.execute('SELECT COUNT(*) FROM beta_members WHERE campaign=?',(CAMPAIGN,)).fetchone()[0] >= CAPACITY:
                raise ValueError('beta_capacity_reached')
            now = rewards._now()
            db.execute('INSERT INTO beta_members VALUES(?,?,?,?,NULL,NULL)', (CAMPAIGN,uid,rewards._iso(now),rewards._iso(now+timedelta(days=DAYS))))
            db.execute('INSERT INTO admin_audit VALUES(?,?,?,?,?,?)', ('aud_'+secrets.token_urlsafe(12),actor,'beta_enroll',uid,json.dumps({'campaign':CAMPAIGN,'reserved_krw':RESERVED_KRW}),rewards._iso()))
        db.execute('COMMIT')
    return progress(store,uid)


def receipt_terms(db, uid, attribution, purchase):
    member = db.execute('SELECT * FROM beta_members WHERE campaign=? AND uid=?',(CAMPAIGN,uid)).fetchone()
    if not member:
        return None
    start, end = rewards._parse_iso(member['starts_at']), rewards._parse_iso(member['ends_at'])
    if not start <= rewards._now() < end or not start <= purchase < end:
        raise ValueError('beta_outside_period')
    if rewards._parse_iso(attribution['selected_at']) < start:
        raise ValueError('beta_selection_before_enrollment')
    count = db.execute("SELECT COUNT(*) FROM beta_receipts b JOIN receipts r ON r.id=b.receipt_id WHERE b.campaign=? AND b.uid=? AND r.status IN ('pending','approved')",(CAMPAIGN,uid)).fetchone()[0]
    if count >= RECEIPTS:
        raise ValueError('beta_receipt_limit_reached')
    return PER_RECEIPT


def progress(store, uid):
    with store._db() as db:
        m = db.execute('SELECT * FROM beta_members WHERE campaign=? AND uid=?',(CAMPAIGN,uid)).fetchone()
        if not m:
            return {'enrolled':False}
        approved = db.execute("SELECT COUNT(*) FROM beta_receipts b JOIN receipts r ON r.id=b.receipt_id WHERE b.campaign=? AND b.uid=? AND r.status='approved'",(CAMPAIGN,uid)).fetchone()[0]
    return {'enrolled':True,'campaign':CAMPAIGN,'starts_at':m['starts_at'],'ends_at':m['ends_at'],
            'approved_receipts':approved,'required_receipts':COMPLETION_RECEIPTS,'receipt_limit':RECEIPTS,'survey_submitted':bool(m['survey_at']),
            'bonus_eligible':approved>=COMPLETION_RECEIPTS and bool(m['survey_at']) and rewards._now() >= rewards._parse_iso(m['ends_at']), 'bonus_krw':BONUS,
            'reserved_max_krw':RESERVED_KRW,'bonus_payout_available':True}


def survey(store, uid, answer):
    text = answer.strip()
    if not 10 <= len(text) <= 2000:
        raise ValueError('survey_length_invalid')
    with rewards._LOCK, store._db() as db:
        db.execute('BEGIN IMMEDIATE')
        m = db.execute('SELECT * FROM beta_members WHERE campaign=? AND uid=?',(CAMPAIGN,uid)).fetchone()
        if not m:
            raise ValueError('beta_enrollment_required')
        if rewards._now() >= rewards._parse_iso(m['ends_at']):
            raise ValueError('beta_outside_period')
        db.execute('UPDATE beta_members SET survey=?,survey_at=? WHERE campaign=? AND uid=? AND survey_at IS NULL',(text,rewards._iso(),CAMPAIGN,uid))
        db.execute('COMMIT')
    return progress(store,uid)


def request_bonus(store, uid, request_id, bank, account, holder):
    from . import payouts
    import re
    if not uid.startswith('kakao_'):
        raise ValueError('linked_account_required')
    account = re.sub(r'[ -]', '', account)
    if not re.fullmatch(r'[0-9]{8,20}', account) or not bank.strip() or not holder.strip():
        raise ValueError('invalid_bank_details')
    encrypted = payouts.cipher().encrypt(json.dumps({'bank':bank.strip(),'account':account,'holder':holder.strip()},ensure_ascii=False).encode()).decode()
    with rewards._LOCK, store._db() as db:
        db.execute('BEGIN IMMEDIATE')
        old = db.execute('SELECT * FROM beta_payouts WHERE uid=? AND request_id=?',(uid,request_id)).fetchone()
        if old:
            return payouts.public(old)
        member = db.execute('SELECT * FROM beta_members WHERE campaign=? AND uid=?',(CAMPAIGN,uid)).fetchone()
        count = db.execute("SELECT COUNT(*) FROM beta_receipts b JOIN receipts r ON r.id=b.receipt_id WHERE b.campaign=? AND b.uid=? AND r.status='approved'",(CAMPAIGN,uid)).fetchone()[0]
        if not member or not member['survey_at'] or count < COMPLETION_RECEIPTS or rewards._now() < rewards._parse_iso(member['ends_at']):
            raise ValueError('beta_completion_required')
        if db.execute("SELECT 1 FROM beta_payouts WHERE uid=? AND status IN ('pending','processing','paid')",(uid,)).fetchone():
            raise ValueError('payout_already_requested')
        now = rewards._iso()
        award = db.execute('INSERT OR IGNORE INTO beta_awards VALUES(?,?,?)',(CAMPAIGN,uid,now))
        if award.rowcount:
            db.execute('INSERT INTO reward_ledger VALUES(?,?,NULL,?,?,?,?)',('led_'+secrets.token_urlsafe(12),uid,BONUS,'beta_bonus:'+CAMPAIGN,'베타 참여비',now))
        balance = db.execute('SELECT COALESCE(SUM(amount),0) FROM reward_ledger WHERE uid=?',(uid,)).fetchone()[0]
        if balance < BONUS:
            raise ValueError('insufficient_balance')
        ident = 'bpay_'+secrets.token_urlsafe(12)
        db.execute('INSERT INTO beta_payouts (id,uid,request_id,receipt_id,amount_krw,recipient_encrypted,account_tail,created_at,updated_at) VALUES(?,?,?,NULL,?,?,?,?,?)',(ident,uid,request_id,BONUS,encrypted,account[-4:],now,now))
        db.execute('INSERT INTO reward_ledger VALUES(?,?,NULL,?,?,?,?)',('led_'+secrets.token_urlsafe(12),uid,-BONUS,'payout_hold:'+ident,ident,now))
        db.execute('COMMIT')
        return payouts.public(db.execute('SELECT * FROM beta_payouts WHERE id=?',(ident,)).fetchone())


def roster(store):
    with store._db() as db:
        rows = db.execute('SELECT uid,starts_at,ends_at,survey_at FROM beta_members WHERE campaign=? ORDER BY starts_at',(CAMPAIGN,)).fetchall()
        applications = db.execute('SELECT uid,created_at FROM beta_applications WHERE campaign=? AND uid NOT IN (SELECT uid FROM beta_members WHERE campaign=?) ORDER BY created_at',(CAMPAIGN,CAMPAIGN)).fetchall()
    return {'capacity':CAPACITY,'selected':len(rows),'reserved_max_krw':len(rows)*RESERVED_KRW,
            'budget_max_krw':CAPACITY*RESERVED_KRW,'members':[dict(r) for r in rows], 'applications':[dict(r) for r in applications]}


def apply(store,uid):
    if not uid.startswith('kakao_'):
        raise ValueError('linked_account_required')
    with rewards._LOCK, store._db() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT COUNT(*) FROM beta_members WHERE campaign=?',(CAMPAIGN,)).fetchone()[0] >= CAPACITY:
            raise ValueError('beta_capacity_reached')
        if db.execute('SELECT COUNT(*) FROM beta_applications WHERE campaign=?',(CAMPAIGN,)).fetchone()[0] >= 200:
            raise ValueError('beta_application_capacity_reached')
        db.execute('INSERT OR IGNORE INTO beta_applications VALUES(?,?,?)',(CAMPAIGN,uid,rewards._iso()))
        db.execute('COMMIT')
    return {'ok':True,'status':'applied','message':'신청 접수, 선정 전이며 지급 대상이 아닙니다.'}


def application_status(store, uid):
    with store._db() as db:
        row = db.execute('SELECT created_at FROM beta_applications WHERE campaign=? AND uid=?', (CAMPAIGN, uid)).fetchone()
    return {'applied': bool(row), 'created_at': row['created_at'] if row else None}
