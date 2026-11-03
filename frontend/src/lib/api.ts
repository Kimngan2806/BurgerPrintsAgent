export async function sendMessageSync(sessionId: string, message: string) {
  const url = getApiBaseUrl();
  const res = await fetch(`${url}/api/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ message, session_id: sessionId }),
  });
  
  if (!res.ok) {
    throw new Error('Failed to send message');
  }
  return res.json();
}

export function getApiBaseUrl(): string {
  const configuredUrl = process.env.NEXT_PUBLIC_API_URL;
  if (configuredUrl && !configuredUrl.includes('localhost') && !configuredUrl.includes('ngrok')) {
    return configuredUrl;
  }

  // Luôn dùng relative path để Next.js proxy sang 8000
  return '';
}

export function generateSessionId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // Fallback for older browsers
  return 'sess-' + Math.random().toString(36).substring(2, 15);
}
