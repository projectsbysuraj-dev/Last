const { createClient } = require('@supabase/supabase-js');
const { verifyTelegramWebAppData } = require('./_verify');

const supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_KEY);

module.exports = async (req, res) => {
  if (req.method !== 'POST') {
    return res.status(405).json({ success: false, message: 'Method not allowed' });
  }

  const initData = req.headers['x-telegram-init-data'];
  const user = verifyTelegramWebAppData(initData, process.env.BOT_TOKEN);

  if (!user) {
    return res.status(401).json({ success: false, message: 'Invalid Telegram signature' });
  }

  const { data, error } = await supabase.rpc('spin_wheel', { p_telegram_id: user.id });

  if (error) {
    console.error('spin_wheel RPC error:', error);
    return res.status(500).json({ success: false, message: 'Spin failed, try again' });
  }

  res.status(200).json(data); // { success, won_amount, wallet, spins_available, spins_earned_total, message? }
};
