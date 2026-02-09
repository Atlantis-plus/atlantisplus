import { useState, useRef } from 'react';
import { useAuth } from '../hooks/useAuth';
import { api } from '../lib/api';

type Page = 'home' | 'notes' | 'search' | 'people' | 'chat';

interface HomePageProps {
  onNavigate?: (page: Page) => void;
}

interface LinkedInContact {
  first_name: string;
  last_name: string;
  email: string | null;
  company: string | null;
  position: string | null;
  connected_on: string | null;
}

interface PreviewData {
  total_contacts: number;
  with_email: number;
  without_email: number;
  sample: LinkedInContact[];
}

interface ImportResult {
  imported: number;
  skipped: number;
  duplicates_found: number;
}

export const HomePage = ({ onNavigate }: HomePageProps) => {
  const { displayName, isAuthenticated, loading, error } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setSelectedFile(file);
    setPreview(null);
    setImportResult(null);
    setErrorMsg(null);
    setIsLoading(true);

    try {
      const previewData = await api.previewLinkedInImport(file);
      setPreview(previewData);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to preview file');
    } finally {
      setIsLoading(false);
    }
  };

  const handleImport = async () => {
    if (!selectedFile) return;

    setIsLoading(true);
    setErrorMsg(null);

    try {
      const result = await api.importLinkedIn(selectedFile, true);
      setImportResult(result);
      setPreview(null);
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Import failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleReset = () => {
    setSelectedFile(null);
    setPreview(null);
    setImportResult(null);
    setErrorMsg(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  if (loading) {
    return (
      <div className="page">
        <div className="loading">Loading...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page">
        <div className="error">
          <h2>Error</h2>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <header className="header">
        <h1>Atlantis Plus</h1>
        <p className="subtitle">Personal Network Memory</p>
      </header>

      <main className="main">
        {isAuthenticated ? (
          <>
            <div className="welcome">
              <p>Welcome, <strong>{displayName}</strong>!</p>
            </div>

            {/* LinkedIn Import Section */}
            <div className="import-section">
              <h2>Import LinkedIn Contacts</h2>

              <div className="import-instructions">
                <p>To export your LinkedIn connections:</p>
                <ol>
                  <li>Go to LinkedIn Settings</li>
                  <li>Click "Get a copy of your data"</li>
                  <li>Select "Connections"</li>
                  <li>Download and upload here</li>
                </ol>
              </div>

              {!preview && !importResult && (
                <div className="file-upload">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv"
                    onChange={handleFileSelect}
                    disabled={isLoading}
                    id="csv-upload"
                    style={{ display: 'none' }}
                  />
                  <label htmlFor="csv-upload" className="upload-btn">
                    {isLoading ? 'Loading...' : 'Upload CSV File'}
                  </label>
                </div>
              )}

              {errorMsg && (
                <div className="error-message">
                  {errorMsg}
                  <button onClick={handleReset} className="retry-btn">Try Again</button>
                </div>
              )}

              {preview && (
                <div className="preview-section">
                  <h3>Preview</h3>
                  <div className="preview-stats">
                    <div className="stat">
                      <span className="stat-value">{preview.total_contacts}</span>
                      <span className="stat-label">Total Contacts</span>
                    </div>
                    <div className="stat">
                      <span className="stat-value">{preview.with_email}</span>
                      <span className="stat-label">With Email</span>
                    </div>
                    <div className="stat">
                      <span className="stat-value">{preview.without_email}</span>
                      <span className="stat-label">Without Email</span>
                    </div>
                  </div>

                  <div className="preview-sample">
                    <h4>Sample Contacts:</h4>
                    <ul>
                      {preview.sample.map((contact, i) => (
                        <li key={i}>
                          <strong>{contact.first_name} {contact.last_name}</strong>
                          {contact.company && <span> - {contact.company}</span>}
                          {contact.position && <span> ({contact.position})</span>}
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div className="preview-actions">
                    <button
                      onClick={handleImport}
                      className="import-btn"
                      disabled={isLoading}
                    >
                      {isLoading ? 'Importing...' : `Import ${preview.total_contacts} Contacts`}
                    </button>
                    <button onClick={handleReset} className="cancel-btn">
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {importResult && (
                <div className="import-result">
                  <h3>Import Complete!</h3>
                  <div className="result-stats">
                    <div className="stat success">
                      <span className="stat-value">{importResult.imported}</span>
                      <span className="stat-label">Imported</span>
                    </div>
                    {importResult.duplicates_found > 0 && (
                      <div className="stat warning">
                        <span className="stat-value">{importResult.duplicates_found}</span>
                        <span className="stat-label">Duplicates Skipped</span>
                      </div>
                    )}
                  </div>
                  <div className="result-actions">
                    <button
                      onClick={() => onNavigate?.('people')}
                      className="view-btn"
                    >
                      View Contacts
                    </button>
                    <button onClick={handleReset} className="another-btn">
                      Import More
                    </button>
                  </div>
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="dev-mode">
            <p>Development mode</p>
            <p className="hint">Open in Telegram Mini App for full functionality</p>
          </div>
        )}
      </main>
    </div>
  );
};
