// lib/fetchUtils.ts

interface FetchOptions extends RequestInit {
  timeoutMs?: number;
  retries?: number;
}

export async function fetchWithRetry(url: string, options: FetchOptions = {}): Promise<Response> {
  const { timeoutMs = 8000, retries = 2, ...fetchOptions } = options;

  for (let attempt = 0; attempt <= retries; attempt++) {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(url, {
        ...fetchOptions,
        signal: controller.signal,
      });
      clearTimeout(id);

      // If we get a 500 or 502 (Bad Gateway from Tailscale), throw to trigger a retry
      if (!response.ok && response.status >= 500) {
        throw new Error(`Server error: ${response.status}`);
      }

      return response;
    } catch (error: any) {
      clearTimeout(id);
      
      const isLastAttempt = attempt === retries;
      if (isLastAttempt) {
        throw error;
      }
      
      // Wait a short bit before retrying (exponential backoff: 1s, then 2s)
      await new Promise(resolve => setTimeout(resolve, 1000 * (attempt + 1)));
    }
  }
  
  throw new Error("Fetch failed after all retries");
}