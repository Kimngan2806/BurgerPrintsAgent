export class ApiError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.status = status;
  }
}

const invalidResponse = 'Máy chủ gửi phản hồi không đọc được. Vui lòng chờ một lát rồi thử lại.';
const interruptedStream = 'Kết nối trả lời bị gián đoạn.';

const mediaType = (response: Response) => response.headers.get('content-type')?.split(';', 1)[0].trim().toLowerCase();

export const apiUrl = (path: string) => `${getApiBaseUrl()}/api${path}`;

async function readJson(response: Response): Promise<unknown> {
  const type = mediaType(response);
  if (type === 'application/json' || type?.endsWith('+json')) {
    return response.json().catch(() => undefined);
  }
  return undefined;
}

export async function requestApi(path: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<Response> {
  const form = body instanceof FormData;
  let response: Response;
  try {
    response = await fetch(apiUrl(path), {method, credentials: 'include', signal,
      headers: form ? undefined : {'Content-Type': 'application/json'},
      body: body === undefined ? undefined : form ? body : JSON.stringify(body)});
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new ApiError('Không kết nối được với máy chủ. Vui lòng chờ một lát rồi thử lại.');
  }
  if (response.ok) return response;
  const data = await readJson(response);
  const detail = (data as {detail?: unknown} | undefined)?.detail;
  if (typeof detail === 'string' && detail) throw new ApiError(detail, response.status);
  if (response.status >= 500) {
    throw new ApiError('Máy chủ đang gián đoạn. Vui lòng chờ một lát.', response.status);
  }
  throw new ApiError(`Yêu cầu chưa hoàn tất (${response.status}). Kiểm tra các trường vừa nhập.`, response.status);
}

export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await requestApi(path, method, body);
  const data = await readJson(response);
  if (data === undefined) throw new ApiError(invalidResponse);
  return data as T;
}

export async function readChatStream(response: Response, onAnswer: (answer: string) => void) {
  if (mediaType(response) !== 'text/event-stream' || !response.body) {
    throw new ApiError(invalidResponse);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let answer = '';
  try {
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, {stream: true});
      const events = buffer.split(/\r?\n\r?\n/);
      buffer = events.pop() || '';
      for (const event of events) {
        const value = event.split(/\r?\n/).filter(line => line.startsWith('data:'))
          .map(line => line.slice(5).trimStart()).join('\n');
        if (!value) continue;
        if (value === '[DONE]') return;
        const data = JSON.parse(value) as {type?: unknown; text?: unknown; error?: unknown} | null;
        if (!data || data.type === 'tool_result') continue;
        if (typeof data.text === 'string') answer += data.text;
        else if (typeof data.error === 'string') answer += `\n\n${data.error}`;
        onAnswer(answer);
      }
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
  } finally {
    void reader.cancel().catch(() => {});
    reader.releaseLock();
  }
  throw new ApiError(interruptedStream);
}

export function sendMessageSync(sessionId: string, message: string) {
  return api<{response: string; session_id: string}>('/chat', 'POST', {message, session_id: sessionId});
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
