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

  const { amount, upi_id } = req.body || {};
  if (!amount || !upi_id) {
    return res.status(400).json({ success: false, message: 'Missing amount or UPI ID' });
  }

  const { error } = await supabase.from('withdrawals').insert({
    telegram_id: user.id,
    amount,
    upi_id,
    status: 'pending',
  });

  if (error) {
    console.error('Withdrawal insert error:', error);
    return res.status(500).json({ success: false, message: 'Could not submit request' });
  }

  res.status(200).json({ success: true, message: 'Request received (demo, manual review)' });
};
