const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface AuthResponse {
  access_token: string;
  refresh_token: string;
  user_id: string;
  telegram_id: number;
  display_name: string;
}

interface ProcessResponse {
  evidence_id: string;
  status: string;
  message: string;
}

class ApiClient {
  private accessToken: string | null = null;

  setAccessToken(token: string) {
    this.accessToken = token;
    console.log('[API] Access token set');
  }

  hasAccessToken(): boolean {
    return !!this.accessToken;
  }

  getApiUrl(): string {
    return API_URL;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {},
    timeoutMs: number = 30000
  ): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...options.headers as Record<string, string>
    };

    if (this.accessToken) {
      headers['Authorization'] = `Bearer ${this.accessToken}`;
    }

    const url = `${API_URL}${endpoint}`;
    console.log('[API] Request:', { url, method: options.method || 'GET', hasToken: !!this.accessToken, body: options.body });

    // Create AbortController for timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(url, {
        ...options,
        headers,
        mode: 'cors',
        credentials: 'omit',
        signal: controller.signal
      });

      clearTimeout(timeoutId);
      console.log('[API] Response status:', response.status);

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(error.detail || `HTTP ${response.status}`);
      }

      return response.json();
    } catch (err) {
      clearTimeout(timeoutId);

      if (err instanceof Error && err.name === 'AbortError') {
        console.error('[API] Request timed out after', timeoutMs, 'ms');
        throw new Error('Request timed out');
      }

      console.error('[API] Fetch error:', {
        url,
        error: err,
        name: err instanceof Error ? err.name : 'Unknown',
        message: err instanceof Error ? err.message : 'Unknown'
      });
      throw err;
    }
  }

  async healthCheck(): Promise<{ status: string; environment: string; version: string }> {
    return this.request('/health');
  }

  async authTelegram(initData: string): Promise<AuthResponse> {
    return this.request('/auth/telegram', {
      method: 'POST',
      body: JSON.stringify({ init_data: initData })
    });
  }

  async processVoice(storagePath: string): Promise<ProcessResponse> {
    return this.request('/process/voice', {
      method: 'POST',
      body: JSON.stringify({ storage_path: storagePath })
    });
  }

  async processText(text: string): Promise<ProcessResponse> {
    return this.request('/process/text', {
      method: 'POST',
      body: JSON.stringify({ text })
    });
  }

  async getProcessingStatus(evidenceId: string): Promise<{
    evidence_id: string;
    status: string;
    processed: boolean;
    error_message?: string;
  }> {
    return this.request(`/process/status/${evidenceId}`);
  }
}

export const api = new ApiClient();
