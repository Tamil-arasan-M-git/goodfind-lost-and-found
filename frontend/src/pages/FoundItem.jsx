import { useState } from "react";
import ObjectDetectionSuggestion from "../components/ObjectDetectionSuggestion";
import { apiUrl } from "../api";
import CategorySuggestions from "../components/CategorySuggestions";
import { displayLabel, getCategorySuggestions, REPORT_CATEGORY_OPTIONS, REPORT_CATEGORY_VALUES, validateReportForm } from "../reportForm";

function FoundItem() {
  const [form, setForm] = useState({
    item_name: "",
    category: "",
    description: "",
    item_date: "",
    location: "",
    detection_labels: [],
  });

  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [photo, setPhoto] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});
  const [detections, setDetections] = useState([]);
  const [matches, setMatches] = useState([]);
  const [matching, setMatching] = useState(false);

  function handleChange(event) {
    setFieldErrors((current) => ({ ...current, [event.target.name]: "" }));
    setForm({
      ...form,
      [event.target.name]: event.target.value,
    });
  }

  async function handleSubmit(event) {
    event.preventDefault();

    setMessage("");
    setError("");
    setLoading(true);

    const validationErrors = validateReportForm(form);
    if (Object.keys(validationErrors).length) {
      setFieldErrors(validationErrors);
      setError("Review the highlighted fields and try again.");
      setLoading(false);
      return;
    }

    try {
      const storedUser = localStorage.getItem("goodfind_user");

      if (!storedUser) {
        throw new Error("Please login before reporting a found item.");
      }

      const token = localStorage.getItem("goodfind_access_token");

      const response = await fetch(
        apiUrl("/api/items/found"),
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            item_name: form.item_name.trim(),
            category: form.category.trim(),
            description: form.description.trim(),
            item_date: form.item_date,
            location: form.location.trim(),
            detection_labels: form.detection_labels,
          }),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Failed to report found item");
      }

      if (photo) {
        const imageBody = new FormData();
        imageBody.append("image", photo);
        const imageResponse = await fetch(apiUrl(`/api/items/${data.item.item_id}/image`), {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: imageBody,
        });
        const imageData = await imageResponse.json();
        if (!imageResponse.ok) throw new Error(imageData.detail || "Item reported, but the photo could not be saved.");
      }

      setMatching(true);
      const matchResponse = await fetch(apiUrl(`/api/matches/found/${data.item.item_id}`), {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const matchData = await matchResponse.json();
      if (!matchResponse.ok) throw new Error(matchData.detail || "Item reported, but matching could not be completed.");
      const results = matchData.matches || [];
      setMatches(results);
      setMessage(results.length ? "Found item reported. Potential lost-item reports were found for review." : "Found item reported successfully. No active potential matches were found yet.");

      setForm({
        item_name: "",
        category: "",
        description: "",
        item_date: "",
        location: "",
        detection_labels: [],
      });
      setPhoto(null);
    } catch (error) {
      setError(error.message);
    } finally {
      setLoading(false);
      setMatching(false);
    }
  }

  return (
    <div className="report-page">
      <div className="report-container">
        <div className="report-header">
          <p className="section-label">REPORT A FOUND ITEM</p>

          <h1>Tell us what you found</h1>

          <p>
            Provide some details about the item you found. These details
            will help GoodFind identify the person who may have lost it.
          </p>
        </div>

        <form className="report-form" onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="item-name">Item name</label><small>Use a clear name, for example “Blue water bottle”.</small>

            <input
              id="item-name"
              name="item_name"
              type="text"
              value={form.item_name}
              onChange={handleChange}
              placeholder="Blue water bottle"
              required
              aria-invalid={Boolean(fieldErrors.item_name)} aria-describedby="found-name-error"
            />
            {fieldErrors.item_name && <span id="found-name-error" className="field-error">{fieldErrors.item_name}</span>}
          </div>

          <ObjectDetectionSuggestion
            labels={form.detection_labels}
            onLabelsChange={(detection_labels) => setForm({ ...form, detection_labels })}
            onFileChange={setPhoto}
            onApplyItemName={(label) => setForm((current) => ({ ...current, item_name: displayLabel(label) }))}
            onDetectionsChange={setDetections}
          />

          <div className="form-group">
            <label htmlFor="category">Category</label><small>Choose the category that best describes the item. You can do this before adding a photo.</small>

            <select
              id="category"
              name="category"
              value={form.category}
              onChange={handleChange}
              required
              aria-invalid={Boolean(fieldErrors.category)} aria-describedby="found-category-error"
            >
              <option value="">Select a category</option>
              {REPORT_CATEGORY_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            {fieldErrors.category && <span id="found-category-error" className="field-error">{fieldErrors.category}</span>}
            <CategorySuggestions suggestions={getCategorySuggestions(detections, REPORT_CATEGORY_VALUES)} onUse={(category) => setForm((current) => ({ ...current, category }))} />
          </div>

          <div className="form-group">
            <label htmlFor="description">Description</label>

            <textarea
              id="description"
              name="description"
              rows="5"
              value={form.description}
              onChange={handleChange}
              placeholder="Describe the item, color, brand, unique features, etc."
            ></textarea>
            <small>Include color, brand, or non-sensitive distinguishing details. Do not include contact or ID numbers.</small>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="found-date">Date Found</label>

              <input
                id="found-date"
                name="item_date"
                type="date"
                value={form.item_date}
                onChange={handleChange}
                required
                aria-invalid={Boolean(fieldErrors.item_date)} aria-describedby="found-date-error"
              />
              {fieldErrors.item_date && <span id="found-date-error" className="field-error">{fieldErrors.item_date}</span>}
            </div>

            <div className="form-group">
              <label htmlFor="found-location">Location Found</label>

              <input
                id="found-location"
                name="location"
                type="text"
                value={form.location}
                onChange={handleChange}
                placeholder="Example: College library"
                required
                aria-invalid={Boolean(fieldErrors.location)} aria-describedby="found-location-error"
              />
              {fieldErrors.location && <span id="found-location-error" className="field-error">{fieldErrors.location}</span>}
            </div>
          </div>

          {message && <p className="success-message" role="status">{message}</p>}

          {error && <p className="error-message" role="alert">{error}</p>}

          <button
            type="submit"
            className="primary-button submit-button"
            disabled={loading}
          >
            {loading ? "Submitting..." : "Submit Found Item Report"}
          </button>
        </form>
        {matching && <p className="loading-state" role="status">Looking for possible lost-item reports…</p>}
        {!matching && matches.length > 0 && <section className="matches-section" aria-label="Potential lost item matches">
          <p className="section-label">POTENTIAL MATCHES</p>
          <h2>Lost reports worth reviewing</h2>
          <p>These are suggestions based on report details. They do not confirm ownership or reveal the reporter’s identity.</p>
          {matches.map((match) => <article className="match-card" key={match.match_id}>
            <h3>{match.lost_item?.item_name || "Lost item"}</h3>
            <p><strong>Category:</strong> {match.lost_item?.category || "Not specified"}</p>
            <p><strong>Location:</strong> {match.lost_item?.location || "Not specified"}</p>
            <p><strong>Score:</strong> {Number(match.similarity_score || 0).toFixed(1)}%</p>
            <p><strong>Why it was suggested:</strong> Name {match.explanation?.components?.name ?? "N/A"}%, category {match.explanation?.category_match ? "matches" : "does not match"}.</p>
          </article>)}
        </section>}
      </div>
    </div>
  );
}

export default FoundItem;
