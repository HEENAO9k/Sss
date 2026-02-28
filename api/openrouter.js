export default async function handler(req, res) {
  // CORS preflight
  if (req.method === 'OPTIONS') {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST,OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    return res.status(204).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const { model, wordCount } = req.body || {};
    const count = parseInt(wordCount, 10) || 50;

    const API_KEY = process.env.OPENROUTER_API_KEY;
    if (!API_KEY) {
      return res.status(500).json({ error: 'OpenRouter API key is not configured on the server.' });
    }

    const prompt = `Generate exactly ${count} common English words in alphabetical order (A-Z).

Requirements:
- Sort words alphabetically from A to Z
- Each word should be 3-12 letters long
- Use common, everyday English words (nouns, verbs, adjectives)
- No proper nouns, no abbreviations
- Words should be suitable for all ages
- Try to distribute words across the alphabet evenly
- Output ONLY the words, one per line
- NO numbering, NO bullets, NO extra text

Generate ${count} words now sorted A-Z (ONLY words, one per line):`;

    const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${API_KEY}`
      },
      body: JSON.stringify({
        model: model || 'google/gemini-2.0-flash-exp:free',
        messages: [{ role: 'user', content: prompt }],
        temperature: 0.8,
        max_tokens: Math.min(count * 15, 8000)
      })
    });

    const data = await response.json();

    if (!response.ok) {
      return res.status(500).json({ error: data.error?.message || JSON.stringify(data) });
    }

    const content = data.choices?.[0]?.message?.content || '';
    res.setHeader('Access-Control-Allow-Origin', '*');
    return res.status(200).json({ success: true, content });
  } catch (err) {
    console.error('Proxy error:', err);
    res.setHeader('Access-Control-Allow-Origin', '*');
    return res.status(500).json({ error: err.message || 'Internal server error' });
  }
}