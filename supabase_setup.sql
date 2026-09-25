-- Run this in Supabase SQL Editor (after your existing users/transactions/withdrawals tables exist)

-- 1. Enable RLS on all tables
alter table users enable row level security;
alter table transactions enable row level security;
alter table withdrawals enable row level security;

-- 2. Allow the browser (anon key) to READ users and transactions
--    Note: since there is no backend verifying WHO is asking, this allows
--    reading any row by telegram_id — fine for a demo app where the id
--    itself isn't sensitive, but do not put sensitive data in these tables.
create policy "public read users" on users for select using (true);
create policy "public read transactions" on transactions for select using (true);

-- 3. Allow inserting withdrawal requests, but NOT reading other people's
create policy "public insert withdrawals" on withdrawals for insert with check (true);

-- 4. Grants: anon key can only do what's listed here
grant usage on schema public to anon;
grant select on users to anon;
grant select on transactions to anon;
grant insert on withdrawals to anon;

-- 5. RPC function: spin_wheel
--    Wallet/spin changes go through this function ONLY — the browser can
--    never directly UPDATE the users table (no update policy exists),
--    so this is the only way spins/wallet can change from the frontend.
create or replace function spin_wheel(p_telegram_id bigint)
returns json
language plpgsql
security definer
as $$
declare
  v_spins int;
  v_wallet numeric;
  v_spins_total int;
  v_win numeric := 5.00;
begin
  select spins_available, wallet, spins_earned_total
    into v_spins, v_wallet, v_spins_total
    from users where telegram_id = p_telegram_id
    for update;

  if v_spins is null then
    return json_build_object('success', false, 'message', 'User not found — open the app via the Telegram bot first.');
  end if;

  if v_spins <= 0 then
    return json_build_object('success', false, 'message', 'No spins left. Refer a friend to get +1 spin!');
  end if;

  update users
    set spins_available = spins_available - 1,
        wallet = wallet + v_win
    where telegram_id = p_telegram_id;

  insert into transactions (telegram_id, title, amount, type)
    values (p_telegram_id, 'Lucky Spin Win (₹' || v_win || ')', v_win, 'credit');

  return json_build_object(
    'success', true,
    'won_amount', v_win,
    'wallet', v_wallet + v_win,
    'spins_available', v_spins - 1,
    'spins_earned_total', v_spins_total
  );
end;
$$;

grant execute on function spin_wheel(bigint) to anon;

-- ⚠️ SECURITY NOTE:
-- This setup has no server-side proof of WHO is calling it — anyone who
-- knows (or guesses) a telegram_id could call spin_wheel() for that id, or
-- insert fake withdrawal requests. Fine for a demo/testing app with no real
-- money. Before handling real money, add a small serverless function
-- (e.g. a Vercel Function) that verifies Telegram's initData signature
-- before calling this RPC — ask me for that when you're ready.
