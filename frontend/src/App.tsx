import React, { useEffect, useMemo, useState } from "react";
import { apiClient, getAbsoluteUrl } from "./api";

interface PredictionCreateResponse {
  id: string;
  url: string;
  status: string;
}

interface PredictionDetailResponse {
  id: string;
  url: string;
  status: string;
  files: string[];
  num_outputs: number;
}

const App: React.FC = () => {
  const [prompt, setPrompt] = useState("");
  const [numOutputs, setNumOutputs] = useState(2);
  const [outputFormat, setOutputFormat] = useState("jpg");
  const [requireTriggerWord, setRequireTriggerWord] = useState(true);
  const [triggerWord, setTriggerWord] = useState("TOK");

  const [currentPredictionId, setCurrentPredictionId] = useState<string | null>(
    null
  );
  const [predictionStatus, setPredictionStatus] = useState<string | null>(null);
  const [predictionFiles, setPredictionFiles] = useState<string[]>([]);
  const [displayNumOutputs, setDisplayNumOutputs] = useState<number | null>(
    null
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [zoomedImageUrl, setZoomedImageUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!zoomedImageUrl) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setZoomedImageUrl(null);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [zoomedImageUrl]);

  const hasActivePrediction = useMemo(
    () => currentPredictionId !== null,
    [currentPredictionId]
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!prompt.trim()) {
      setError("Please enter a prompt.");
      return;
    }

    setIsSubmitting(true);
    setPredictionFiles([]);
    setPredictionStatus("starting");
    setDisplayNumOutputs(numOutputs);

    try {
      const body = {
        prompt,
        num_outputs: numOutputs,
        output_format: outputFormat,
        require_trigger_word: requireTriggerWord,
        trigger_word: triggerWord,
      };

      const response = await apiClient.post<PredictionCreateResponse>(
        "/generate",
        body
      );

      setCurrentPredictionId(response.data.id);
      setPredictionStatus(response.data.status);
    } catch (err: any) {
      setError(
        err?.response?.data?.detail || "Failed to start generation. Try again."
      );
      setCurrentPredictionId(null);
      setPredictionStatus(null);
    } finally {
      setIsSubmitting(false);
    }
  };

  useEffect(() => {
    if (!currentPredictionId) {
      return;
    }

    let isCancelled = false;
    let interval: number | undefined;

    const poll = async () => {
      try {
        const response = await apiClient.get<PredictionDetailResponse>(
          `/predictions/${currentPredictionId}`
        );
        if (isCancelled) return;

        setPredictionStatus(response.data.status);
        if (response.data.num_outputs && response.data.num_outputs > 0) {
          setDisplayNumOutputs(response.data.num_outputs);
        }

        if (response.data.status === "succeeded") {
          setPredictionFiles(response.data.files || []);
          if (interval !== undefined) {
            clearInterval(interval);
          }
        } else if (
          response.data.status === "failed" ||
          response.data.status === "canceled"
        ) {
          setError("Generation failed. Please try again.");
          if (interval !== undefined) {
            clearInterval(interval);
          }
        }
      } catch (err: any) {
        if (!isCancelled) {
          setError("Error while polling prediction status.");
        }
      }
    };

    poll();
    interval = window.setInterval(poll, 3000);

    return () => {
      isCancelled = true;
      if (interval !== undefined) {
        clearInterval(interval);
      }
    };
  }, [currentPredictionId]);

  const displaySlots = useMemo(() => {
    const base = displayNumOutputs ?? numOutputs;
    return base > 0 ? base : 0;
  }, [displayNumOutputs, numOutputs]);

  const isLoading =
    hasActivePrediction &&
    predictionStatus !== "succeeded" &&
    predictionStatus !== "failed" &&
    predictionStatus !== "canceled";

  const handleDownload = async (filePath: string, index: number) => {
    try {
      // S3 URLs are absolute; fetch directly to avoid CORS/API key issues
      const isAbsolute = filePath.startsWith("http://") || filePath.startsWith("https://");
      const blob = isAbsolute
        ? await (await fetch(filePath)).blob()
        : (await apiClient.get(filePath, { responseType: "blob" })).data as Blob;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = currentPredictionId
        ? `${currentPredictionId}-${index}.${filePath.split(".").pop() || "jpg"}`
        : `output-${index}.jpg`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("Download failed.");
    }
  };

  return (
    <div className="app-root">
      {zoomedImageUrl && (
        <div
          className="image-zoom-backdrop"
          onClick={() => setZoomedImageUrl(null)}
          role="presentation"
        >
          <div
            className="image-zoom-content"
            onClick={(e) => e.stopPropagation()}
            role="presentation"
          >
            <button
              type="button"
              className="image-zoom-close"
              onClick={() => setZoomedImageUrl(null)}
              aria-label="Close zoom"
            >
              ×
            </button>
            <img src={zoomedImageUrl} alt="Zoomed output" />
          </div>
        </div>
      )}
      <div className="app-shell">
        <aside className="sidebar">
          <header className="sidebar-header">
            <h1>PhotoMeAI</h1>
            <p className="subtitle">Prompt-based image generation UI</p>
          </header>

          <form className="control-form" onSubmit={handleSubmit}>
            <div className="form-group">
              <label htmlFor="prompt">Prompt</label>
              <textarea
                id="prompt"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={6}
                placeholder="Describe the image you want to generate..."
              />
            </div>

            <div className="panel">
              <div className="panel-header">
                <h2>Settings</h2>
              </div>
              <div className="panel-body">
                <div className="form-row">
                  <div className="form-group-inline">
                    <label htmlFor="numOutputs">Number of images</label>
                    <input
                      id="numOutputs"
                      type="number"
                      min={1}
                      max={4}
                      value={numOutputs}
                      onChange={(e) =>
                        setNumOutputs(
                          Math.min(4, Math.max(1, Number(e.target.value) || 1))
                        )
                      }
                    />
                  </div>
                  <div className="form-group-inline">
                    <label htmlFor="outputFormat">Format</label>
                    <select
                      id="outputFormat"
                      value={outputFormat}
                      onChange={(e) => setOutputFormat(e.target.value)}
                    >
                      <option value="jpg">JPG</option>
                      <option value="png">PNG</option>
                    </select>
                  </div>
                </div>

                <div className="form-group checkbox-group">
                  <label>
                    <input
                      type="checkbox"
                      checked={requireTriggerWord}
                      onChange={(e) => setRequireTriggerWord(e.target.checked)}
                    />
                    <span>Require trigger word</span>
                  </label>
                </div>

                {requireTriggerWord && (
                  <div className="form-group">
                    <label htmlFor="triggerWord">Trigger word</label>
                    <input
                      id="triggerWord"
                      type="text"
                      value={triggerWord}
                      onChange={(e) => setTriggerWord(e.target.value)}
                    />
                  </div>
                )}
              </div>
            </div>

            {error && <div className="error-banner">{error}</div>}

            <button className="primary-button" type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Generating..." : "Generate"}
            </button>
          </form>
        </aside>

        <main className="main-panel">
          <div className="main-header">
            <h2>Outputs</h2>
            {predictionStatus && (
              <span className="status-pill">Status: {predictionStatus}</span>
            )}
          </div>

          {!hasActivePrediction && (
            <div className="empty-state">
              <p>Submit a prompt to see generated images here.</p>
            </div>
          )}

          {hasActivePrediction && (
            <>
              <div className="grid">
                {Array.from({ length: displaySlots }).map((_, index) => {
                  const fileUrl = predictionFiles[index];
                  const src = fileUrl ? getAbsoluteUrl(fileUrl) : undefined;

                  return (
                    <div key={index} className="grid-cell">
                      {src && !isLoading ? (
                        <>
                          <button
                            type="button"
                            className="cell-image-wrap"
                            onClick={() => setZoomedImageUrl(src)}
                            title="Click to zoom"
                          >
                            <img src={src} alt={`Output ${index + 1}`} />
                          </button>
                          <button
                            type="button"
                            className="cell-download"
                            onClick={() => fileUrl && handleDownload(fileUrl, index)}
                            title="Download"
                          >
                            Download
                          </button>
                        </>
                      ) : (
                        <div className="loader">
                          <div className="spinner" />
                          <span>Generating...</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
};

export default App;

