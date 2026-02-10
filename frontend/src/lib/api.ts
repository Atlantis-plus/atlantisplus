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

  async search(query: string): Promise<{
    query: string;
    results: Array<{
      person_id: string;
      display_name: string;
      relevance_score: number;
      reasoning: string;
      matching_facts: string[];
    }>;
    reasoning_summary: string;
  }> {
    return this.request('/search', {
      method: 'POST',
      body: JSON.stringify({ query })
    });
  }

  async chat(message: string, sessionId?: string): Promise<{
    session_id: string;
    message: string;
    tool_results?: Array<{
      tool: string;
      args: Record<string, unknown>;
      result: string;
    }>;
  }> {
    return this.request('/chat', {
      method: 'POST',
      body: JSON.stringify({ message, session_id: sessionId })
    }, 60000); // 60s timeout for chat
  }

  async getChatSessions(): Promise<{
    sessions: Array<{
      session_id: string;
      title: string;
      created_at: string;
      updated_at: string;
    }>;
  }> {
    return this.request('/chat/sessions');
  }

  async getChatMessages(sessionId: string): Promise<{
    messages: Array<{
      message_id: string;
      role: string;
      content: string;
      created_at: string;
    }>;
  }> {
    return this.request(`/chat/sessions/${sessionId}/messages`);
  }

  async previewLinkedInImport(file: File): Promise<{
    total_contacts: number;
    with_email: number;
    without_email: number;
    sample: Array<{
      first_name: string;
      last_name: string;
      email: string | null;
      company: string | null;
      position: string | null;
      connected_on: string | null;
    }>;
  }> {
    const formData = new FormData();
    formData.append('file', file);

    const headers: Record<string, string> = {};
    if (this.accessToken) {
      headers['Authorization'] = `Bearer ${this.accessToken}`;
    }

    const response = await fetch(`${API_URL}/import/linkedin/preview`, {
      method: 'POST',
      headers,
      body: formData,
      mode: 'cors',
      credentials: 'omit'
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  async importLinkedIn(file: File, skipDuplicates: boolean = true): Promise<{
    imported: number;
    skipped: number;
    duplicates_found: number;
    updated: number;
    batch_id: string;
    evidence_id: string;
    analytics: {
      by_year: Record<string, number>;
      by_company: Record<string, number>;
      with_email: number;
      without_email: number;
      total: number;
    };
    details: Array<{
      name: string;
      status: string;
      reason?: string;
      company?: string;
      position?: string;
    }>;
    dedup_result: {
      checked?: number;
      duplicates_found?: number;
      error?: string;
    } | null;
  }> {
    const formData = new FormData();
    formData.append('file', file);

    const headers: Record<string, string> = {};
    if (this.accessToken) {
      headers['Authorization'] = `Bearer ${this.accessToken}`;
    }

    const url = `${API_URL}/import/linkedin?skip_duplicates=${skipDuplicates}`;

    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: formData,
      mode: 'cors',
      credentials: 'omit'
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  async previewCalendarImport(file: File, ownerEmail?: string): Promise<{
    total_events: number;
    events_with_attendees: number;
    unique_attendees: number;
    date_range: string;
    top_attendees: Array<{
      email: string;
      name: string | null;
      meeting_count: number;
    }>;
    sample_events: Array<{
      summary: string;
      date: string;
      attendee_count: number;
      attendees: string[];
    }>;
  }> {
    const formData = new FormData();
    formData.append('file', file);
    if (ownerEmail) {
      formData.append('owner_email', ownerEmail);
    }

    const headers: Record<string, string> = {};
    if (this.accessToken) {
      headers['Authorization'] = `Bearer ${this.accessToken}`;
    }

    const url = ownerEmail
      ? `${API_URL}/import/calendar/preview?owner_email=${encodeURIComponent(ownerEmail)}`
      : `${API_URL}/import/calendar/preview`;

    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: formData,
      mode: 'cors',
      credentials: 'omit'
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  async importCalendar(file: File, ownerEmail?: string): Promise<{
    imported_people: number;
    imported_meetings: number;
    skipped_duplicates: number;
    updated_existing: number;
    batch_id: string;
    evidence_id: string;
    analytics: {
      by_frequency: Record<string, number>;
      date_range: string;
      top_domains: Record<string, number>;
      top_attendees: Array<{ email: string; name: string | null; meetings: number }>;
      total_events: number;
      total_people: number;
    };
    dedup_result: {
      checked?: number;
      duplicates_found?: number;
      error?: string;
    } | null;
  }> {
    const formData = new FormData();
    formData.append('file', file);

    const headers: Record<string, string> = {};
    if (this.accessToken) {
      headers['Authorization'] = `Bearer ${this.accessToken}`;
    }

    const url = ownerEmail
      ? `${API_URL}/import/calendar?owner_email=${encodeURIComponent(ownerEmail)}`
      : `${API_URL}/import/calendar`;

    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: formData,
      mode: 'cors',
      credentials: 'omit'
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }
}

export const api = new ApiClient();
