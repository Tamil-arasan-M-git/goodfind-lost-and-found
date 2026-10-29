import { useEffect, useRef, useState } from "react";
import { apiUrl } from "../api";

function ObjectDetectionSuggestion({ onLabelsChange, onFileChange, onApplyItemName, onDetectionsChange }) {
  const [file, setFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [detections, setDetections] = useState([]);
  const inputRef = useRef(null);

  const previewUrlRef = useRef("");

  useEffect(() => () => {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
  }, []);

  function replacePreview(nextFile) {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    previewUrlRef.current = nextFile ? URL.createObjectURL(nextFile) : "";
    setPreviewUrl(previewUrlRef.current);
  }

  function clearSelection() {
    setFile(null);
    replacePreview(null);
    onFileChange?.(null);
    setDetections([]);
    onDetectionsChange?.([]);
    setError("");
    onLabelsChange([]);
    if (inputRef.current) inputRef.current.value = "";
  }

  function selectFile(selectedFile) {

    if (!selectedFile) {
      clearSelection();
      return;
    }

    const supportedTypes = ["image/jpeg", "image/png", "image/webp"];
    if (!supportedTypes.includes(selectedFile.type)) {
      clearSelection();
      setError("Choose a JPEG, PNG, or WebP image.");
      return;
    }

    if (selectedFile.size > 5 * 1024 * 1024) {
      clearSelection();
      setError("Choose an image smaller than 5 MB.");
      return;
    }

    setFile(selectedFile);
    replacePreview(selectedFile);
    onFileChange?.(selectedFile);
    setDetections([]);
    onDetectionsChange?.([]);
    setError("");
    onLabelsChange([]);
  }

  function handleFileChange(event) {
    selectFile(event.target.files?.[0] || null);
  }

  function handleDrop(event) {
    event.preventDefault();
    selectFile(event.dataTransfer.files?.[0] || null);
  }

  async function detect() {
    if (!file) return;
    setLoading(true);
    setError("");
    try {
      const body = new FormData();
      body.append("image", file);
      const response = await fetch(apiUrl("/api/detections"), {
        method: "POST",
        headers: { Authorization: `Bearer ${localStorage.getItem("goodfind_access_token")}` },
        body,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not detect objects");
      const returnedDetections = Array.isArray(data.detections) ? data.detections : [];
      setDetections(returnedDetections);
      onDetectionsChange?.(returnedDetections);
      onLabelsChange([...new Set(returnedDetections.map((detection) => detection.label))]);
      if (returnedDetections.length === 0) setError("No supported objects were detected. You can still complete the report manually.");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return <div className="form-group image-analysis-group">
    <label htmlFor="item-image">Image analysis <span className="optional-label">(optional)</span></label>
    <div className="upload-dropzone" onDragOver={(event) => event.preventDefault()} onDrop={handleDrop}>
      <span className="upload-icon" aria-hidden="true">↑</span>
      <label htmlFor="item-image" className="upload-label">Choose an image <span>or drop it here</span></label>
      <input
        ref={inputRef}
        id="item-image"
        type="file"
        accept="image/jpeg,image/png,image/webp"
        onChange={handleFileChange}
        aria-describedby="item-image-help item-image-error"
      />
    </div>
    <small id="item-image-help">JPEG, PNG, or WebP up to 5 MB. Analysis runs in memory. If you submit the report, the selected photo is saved with that report using an opaque server-generated reference. AI suggestions are not proof of an item match.</small>

    {previewUrl && (
      <div className="image-preview" aria-label="Selected image preview">
        <img src={previewUrl} alt={`Selected image: ${file?.name || "upload"}`} onError={() => setError("We could not preview that image. Please choose another file.")} />
        <div className="image-preview-details">
          <p>{file?.name}</p>
          <button className="text-button" type="button" onClick={clearSelection}>Remove image</button>
        </div>
      </div>
    )}

    <div className="image-analysis-actions">
      <button className="secondary-button detection-button" type="button" onClick={detect} disabled={!file || loading}>
        {loading ? "Analyzing image..." : "Suggest object labels"}
      </button>
      {file && <span className="file-ready">Image ready for analysis</span>}
    </div>

    {detections.length > 0 && <div className="detected-labels" role="status" aria-live="polite"><strong>AI suggestions — review before using:</strong><ul>{detections.map((detection, index) => <li key={`${detection.label}-${index}`}><span>{detection.label.replaceAll("_", " ")} ({Math.round(detection.confidence * 100)}%)</span><button type="button" className="text-button" onClick={() => onApplyItemName?.(detection.label)}>Use as item name</button></li>)}</ul><small>Suggestions are optional and do not confirm ownership or a match.</small></div>}
    {error && <p id="item-image-error" className="error-message" role="alert">{error}</p>}
  </div>;
}

export default ObjectDetectionSuggestion;
