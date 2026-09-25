const { createClient } = require('@supabase/supabase-js');
const { verifyTelegramWebAppData } = require('./_verify');

const supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_KEY);
const BOT_USERNAME = process.env.BOT_USERNAME;

module.exports = async (req, res) => {
  const initData = req.headers['x-telegram-init-data'] || req.query.initData;
  const user = verifyTelegramWebAppData(initData, process.env.BOT_TOKEN);

  if (!user) {
    return res.status(401).json({ success: false, message: 'Invalid Telegram signature' });
  }

  const telegramId = user.id;

  const { data: userRow } = await supabase
    .from('users')
    .select('*')
    .eq('telegram_id', telegramId)
    .single();

  if (!userRow) {
    return res.status(404).json({ success: false, message: 'User not found — open via /start in the bot first' });
  }

  const { count } = await supabase
    .from('users')
    .select('*', { count: 'exact', head: true })
    .eq('referred_by', telegramId);

  const { data: txs } = await supabase
    .from('transactions')
    .select('*')
    .eq('telegram_id', telegramId)
    .order('created_at', { ascending: false })
    .limit(20);

  res.status(200).json({
    success: true,
    telegram_id: telegramId,
    name: userRow.name,
    wallet: userRow.wallet,
    spins_available: userRow.spins_available,
    spins_earned_total: userRow.spins_earned_total,
    referral_count: count || 0,
    referral_link: `https://t.me/${BOT_USERNAME}?start=${telegramId}`,
    transactions: txs || [],
  });
};
