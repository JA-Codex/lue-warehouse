
-- US-1.4: the calendar and the small static dimensions, loaded once, up front.
-- Run as lue_etl in "lue_warehouse" (python scripts/db_load_reference.py). Safe to re-run: a second
-- run changes nothing and uses no extra surrogate key numbers.
--
-- Not in sql/10_ddl on purpose: that folder holds structure only, and scripts/check_contract.py
-- compares it row for row with the frozen Phase 1 pack. This folder holds data loads.
--
-- Members follow the Phase 1 pack (data dictionary, tools/model.py) and etl/reference_data.py,
-- which scripts/test_reference.py compares with what is loaded here.

-- ---------------------------------------------------------------- dim_date
-- 2023-07-01 to 2027-06-30 = 1,461 days. date_key is YYYYMMDD. Names come from arrays, not
-- to_char(), so the result does not depend on the server's language setting.
-- Holiday and Ramadan flags start FALSE; US-6.4 fills them from the S2 holiday register.
-- ON CONFLICT DO NOTHING keeps whatever US-6.4 has already written (Type 1 columns) on a re-run.
insert into lue_dw.dim_date (
    date_key, full_date, day_of_month, day_name, is_weekend, week_of_year, month_no, month_name,
    quarter_no, year_no, fiscal_month_no, fiscal_quarter_no, fiscal_year_label,
    is_public_holiday, holiday_name, is_ramadan)
select
    to_char(c.d, 'YYYYMMDD')::int,
    c.d,
    extract(day from c.d)::smallint,
    (array['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'])
        [extract(dow from c.d)::int + 1],
    extract(dow from c.d) in (0, 6),
    extract(week from c.d)::smallint,
    extract(month from c.d)::smallint,
    (array['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
           'October', 'November', 'December'])[extract(month from c.d)::int],
    extract(quarter from c.d)::smallint,
    extract(year from c.d)::smallint,
    (((extract(month from c.d)::int + 5) % 12) + 1)::smallint,
    ((((extract(month from c.d)::int + 5) % 12) / 3) + 1)::smallint,
    'FY' || fy.start_year || '-' || right((fy.start_year + 1)::text, 2),
    false,
    null,
    false
from (
    select date '2023-07-01' + n as d
    from generate_series(0, date '2027-06-30' - date '2023-07-01') as n
) as c
cross join lateral (
    select extract(year from c.d)::int - case when extract(month from c.d) < 7 then 1 else 0 end
        as start_year
) as fy
on conflict (date_key) do nothing;

-- ---------------------------------------------------------------- dim_payment_method (6)
-- Type 1 dimension: an existing member is corrected in place, a missing member is added.
-- The insert is ordered, so the keys come out 1..6 in the order below.
drop table if exists _ref_payment_method;
create temp table _ref_payment_method as
select * from (values
    (1, 'CASH',   'Cash',          'Cash',            0),
    (2, 'CHEQUE', 'Cheque',        'Cheque',          3),
    (3, 'BANK',   'Bank transfer', 'Bank',            1),
    (4, 'RAAST',  'Raast',         'Instant payment', 0),
    (5, 'JAZZ',   'JazzCash',      'Mobile wallet',   1),
    (6, 'EASY',   'Easypaisa',     'Mobile wallet',   1)
) as v (ord, method_code, method_name, channel_group, typical_settlement_days);

update lue_dw.dim_payment_method d
   set method_name = r.method_name,
       channel_group = r.channel_group,
       typical_settlement_days = r.typical_settlement_days,
       loaded_at = now()
  from _ref_payment_method r
 where d.method_code = r.method_code
   and (d.method_name, d.channel_group, d.typical_settlement_days)
       is distinct from (r.method_name, r.channel_group, r.typical_settlement_days);

insert into lue_dw.dim_payment_method (
    method_code, method_name, channel_group, typical_settlement_days, source_system, batch_id,
    loaded_at)
select r.method_code, r.method_name, r.channel_group, r.typical_settlement_days, 'SEED', 0, now()
  from _ref_payment_method r
 where not exists (select 1 from lue_dw.dim_payment_method d where d.method_code = r.method_code)
 order by r.ord;

drop table _ref_payment_method;

-- ---------------------------------------------------------------- dim_charge_type (6)
drop table if exists _ref_charge_type;
create temp table _ref_charge_type as
select * from (values
    (1, 'RENT',    'Rent',               'Rent'),
    (2, 'SERVICE', 'Service charge',     'Ancillary'),
    (3, 'LATEFEE', 'Late fee',           'Penalty'),
    (4, 'UTILITY', 'Utility',            'Ancillary'),
    (5, 'CREDIT',  'Credit note',        'Credit'),
    (6, 'DEPADJ',  'Deposit adjustment', 'Credit')
) as v (ord, charge_code, charge_type_name, charge_category);

update lue_dw.dim_charge_type d
   set charge_type_name = r.charge_type_name,
       charge_category = r.charge_category,
       loaded_at = now()
  from _ref_charge_type r
 where d.charge_code = r.charge_code
   and (d.charge_type_name, d.charge_category)
       is distinct from (r.charge_type_name, r.charge_category);

insert into lue_dw.dim_charge_type (
    charge_code, charge_type_name, charge_category, source_system, batch_id, loaded_at)
select r.charge_code, r.charge_type_name, r.charge_category, 'SEED', 0, now()
  from _ref_charge_type r
 where not exists (select 1 from lue_dw.dim_charge_type d where d.charge_code = r.charge_code)
 order by r.ord;

drop table _ref_charge_type;

-- ---------------------------------------------------------------- dim_lease_event_type (4)
drop table if exists _ref_lease_event_type;
create temp table _ref_lease_event_type as
select * from (values
    (1, 'SIGN',   'Signed',       false),
    (2, 'RENEW',  'Renewed',      false),
    (3, 'NOTICE', 'Notice given', true),
    (4, 'TERM',   'Terminated',   true)
) as v (ord, event_code, event_name, is_exit_event);

update lue_dw.dim_lease_event_type d
   set event_name = r.event_name,
       is_exit_event = r.is_exit_event,
       loaded_at = now()
  from _ref_lease_event_type r
 where d.event_code = r.event_code
   and (d.event_name, d.is_exit_event) is distinct from (r.event_name, r.is_exit_event);

insert into lue_dw.dim_lease_event_type (
    event_code, event_name, is_exit_event, source_system, batch_id, loaded_at)
select r.event_code, r.event_name, r.is_exit_event, 'SEED', 0, now()
  from _ref_lease_event_type r
 where not exists (
           select 1 from lue_dw.dim_lease_event_type d where d.event_code = r.event_code)
 order by r.ord;

drop table _ref_lease_event_type;

-- ---------------------------------------------------------------- dim_request_flags (8)
-- Junk dimension: every combination of the three flags, nothing else (no special members, as in
-- the pack: all 8 combinations always exist, so a request always finds its row).
-- Keys 1..8 run from "none of the flags" to "all three flags".
insert into lue_dw.dim_request_flags (is_emergency, is_recurring, is_tenant_caused, flags_label)
select f.e, f.r, f.t,
       case when f.e then 'Emergency' else 'Not emergency' end || ' · ' ||
       case when f.r then 'Recurring' else 'Not recurring' end || ' · ' ||
       case when f.t then 'Tenant-caused' else 'Not tenant-caused' end
  from (select e, r, t
          from (values (false), (true)) as a (e)
         cross join (values (false), (true)) as b (r)
         cross join (values (false), (true)) as c (t)) as f
 where not exists (
           select 1 from lue_dw.dim_request_flags d
            where d.is_emergency = f.e and d.is_recurring = f.r and d.is_tenant_caused = f.t)
 order by f.e, f.r, f.t;
