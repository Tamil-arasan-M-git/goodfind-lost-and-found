import { useState } from "react";
import { useNavigate } from "react-router-dom";
import ObjectDetectionSuggestion from "../components/ObjectDetectionSuggestion";
import { apiUrl } from "../api";
import CategorySuggestions from "../components/CategorySuggestions";
import { displayLabel, getCategorySuggestions, REPORT_CATEGORY_OPTIONS, REPORT_CATEGORY_VALUES, validateReportForm } from "../reportForm";

function LostItem() {
  const navigate = useNavigate();

  const storedUser = localStorage.getItem("goodfind_user");
  const user = storedUser ? JSON.parse(storedUser) : null;

  const [form, setForm] = useState({
    item_name: "",
    category: "",
    description: "",
    item_date: "",
    location: "",
    detection_labels: [],
  });

  const [matches, setMatches] = useState([]);
  const [lostItemId, setLostItemId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [matching, setMatching] = useState(false);
  const [submittingClaimId, setSubmittingClaimId] = useState(null);
  const [chatRequestingId, setChatRequestingId] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [photo, setPhoto] = useState(null);
  const [detections, setDetections] = useState([]);
  const token = localStorage.getItem("goodfind_access_token");

  const handleChange = (e) => {
    setFieldErrors((current) => ({ ...current, [e.target.name]: "" }));
    setForm({
      ...form,
      [e.target.name]: e.target.value,
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!user) {
      navigate("/login", {
        state: { from: "/report/lost" },
      });
      return;
    }

    const validationErrors = validateReportForm(form);
    if (Object.keys(validationErrors).length) {
      setFieldErrors(validationErrors);
      setError("Review the highlighted fields and try again.");
      return;
    }

    setLoading(true);
    setError("");
    setMessage("");
    setMatches([]);

    try {
      const response = await fetch(
        apiUrl("/api/items/lost"),
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
        throw new Error(
          data.detail || "Failed to report lost item"
        );
      }

      setLostItemId(data.item.item_id);
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
      setMessage(
        "Lost item reported successfully. Searching for possible matches..."
      );

      await findMatches(data.item.item_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const findMatches = async (itemId) => {
    setMatching(true);

    try {
      const matchResponse = await fetch(
        apiUrl(`/api/matches/lost/${itemId}`),
        {
          method: "POST",
          headers: {
            Accept: "*/*",
            Authorization: `Bearer ${token}`,
          },
        }
      );

      const matchData = await matchResponse.json();

      if (!matchResponse.ok) {
        throw new Error(
          matchData.detail || "Failed to find matches"
        );
      }

      const results = Array.isArray(matchData) ? matchData : matchData.matches || [];

      setMatches(results);

      if (results.length > 0) {
        setMessage("Possible matches found!");
      } else {
        setMessage(
          "Item reported successfully, but no possible matches were found yet."
        );
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setMatching(false);
    }
  };

  const refreshMatches = async () => {
    if (!lostItemId) return;
    setMatching(true);
    setError("");
    try {
      const response = await fetch(apiUrl(`/api/items/${lostItemId}/matches/refresh`), {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Failed to refresh matches");
      setMatches(data.matches || []);
      setMessage(data.matches?.length ? "Potential matches refreshed." : "No active potential matches found yet.");
    } catch (err) {
      setError(err.message);
    } finally {
      setMatching(false);
    }
  };

  const handleSubmitClaim = async (matchId) => {
    if (!user) {
      navigate("/login");
      return;
    }

    setSubmittingClaimId(matchId);
    setError("");
    setMessage("");

    try {
      const response = await fetch(
        apiUrl(`/api/claims/${matchId}`),
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail || "Failed to submit claim"
        );
      }

      setMessage(
        data.already_pending ? "Your claim is already pending review." : "Claim submitted. The found-item reporter can review it in Claims."
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmittingClaimId(null);
    }
  };

  const handleStartChat = async (matchId) => {
    if (!user) {
      navigate("/login");
      return;
    }

    setChatRequestingId(matchId);
    setError("");
    setMessage("");

    try {
      const response = await fetch(apiUrl("/api/chat/requests"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ match_id: matchId }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Failed to start private chat");
      setMessage(data.request?.status === "PENDING" ? "Private chat request is pending their response." : "Private chat request is already being handled.");
    } catch (err) {
      setError(err.message);
    } finally {
      setChatRequestingId(null);
    }
  };

  const handleResolve = async (matchId) => {
    try {
      const response = await fetch(apiUrl(`/api/matches/${matchId}/resolve`), {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not complete this recovery");
      setMessage("Recovery marked as resolved. This item will no longer appear in active matching.");
      setMatches((current) => current.filter((match) => match.match_id !== matchId));
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="page-container report-page">
      <div className="form-container">
        <p className="section-label">REPORT A LOST ITEM</p><h1>Help us find what is missing</h1>

        <p>
          Tell us about the item you lost. GoodFind will search
          for possible matches with reported found items.
        </p>

        {message && <div className="success-message" role="status">{message}</div>}

        {error && <div className="error-message" role="alert">{error}</div>}

        <form onSubmit={handleSubmit} className="report-form">
          <div className="form-group">
            <label htmlFor="item_name">Item name</label><small>Use a clear name, for example “Black house keys”.</small>

            <input
              id="item_name"
              name="item_name"
              type="text"
              value={form.item_name}
              onChange={handleChange}
              placeholder="Black house keys"
              aria-invalid={Boolean(fieldErrors.item_name)} aria-describedby="lost-name-error"
              required
            />
            {fieldErrors.item_name && <span id="lost-name-error" className="field-error">{fieldErrors.item_name}</span>}
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
              aria-invalid={Boolean(fieldErrors.category)} aria-describedby="lost-category-error"
            >
              <option value="">Select a category</option>
              {REPORT_CATEGORY_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            {fieldErrors.category && <span id="lost-category-error" className="field-error">{fieldErrors.category}</span>}
            <CategorySuggestions suggestions={getCategorySuggestions(detections, REPORT_CATEGORY_VALUES)} onUse={(category) => setForm((current) => ({ ...current, category }))} />
          </div>

          <div className="form-group">
            <label htmlFor="description">
              Description
            </label>

            <textarea
              id="description"
              name="description"
              value={form.description}
              onChange={handleChange}
              placeholder="Describe the item, color, brand, identifying marks, etc."
              rows="5"
            />
            <small>Include color, brand, or non-sensitive distinguishing details. Do not include contact or ID numbers.</small>
          </div>

          <div className="form-group">
            <label htmlFor="item_date">
              Date You Lost the Item
            </label>

            <input
              id="item_date"
              name="item_date"
              type="date"
              value={form.item_date}
              onChange={handleChange}
              required
              aria-invalid={Boolean(fieldErrors.item_date)} aria-describedby="lost-date-error"
            />
            {fieldErrors.item_date && <span id="lost-date-error" className="field-error">{fieldErrors.item_date}</span>}
          </div>

          <div className="form-group">
            <label htmlFor="location">
              Location
            </label>

            <input
              id="location"
              name="location"
              type="text"
              value={form.location}
              onChange={handleChange}
              placeholder="Example: College Library"
              required
              aria-invalid={Boolean(fieldErrors.location)} aria-describedby="lost-location-error"
            />
            {fieldErrors.location && <span id="lost-location-error" className="field-error">{fieldErrors.location}</span>}
          </div>

          <button
            type="submit"
            className="primary-button submit-button"
            disabled={loading}
          >
            {loading
              ? "Reporting..."
              : "Submit Lost Item Report"}
          </button>
        </form>

        {lostItemId && (
          <div className="item-info">
            <p>
              <strong>Lost Item ID:</strong>{" "}
              {lostItemId}
            </p>
          </div>
        )}

        {matching && (
          <div className="item-info matching-message">
            Searching for possible matches...
          </div>
        )}

        {matches.length > 0 && (
          <div className="matches-section">
            <p className="section-label">POTENTIAL MATCHES</p>
            <h2>Reports worth reviewing</h2>

            <p>
              These found-item reports were ranked by the existing matching system. Review the details before requesting a private conversation; a score is not proof of ownership.
            </p>
            <button type="button" className="secondary-button compact-button" onClick={refreshMatches} disabled={matching}>Refresh matches</button>

            {matches.map((match) => (
              <div
                className="match-card"
                key={match.match_id}
              >
                <h3>
                  {match.found_item?.item_name ||
                    "Found Item"}
                </h3>

                {match.found_item?.image_url ? <img className="match-image" src={apiUrl(match.found_item.image_url)} alt={`Photo of found ${match.found_item.item_name || "item"}`} /> : <div className="match-image-placeholder">No photo provided</div>}

                <p>
                  <strong>Category:</strong>{" "}
                  {match.found_item?.category || "N/A"}
                </p>

                <p>
                  <strong>Description:</strong>{" "}
                  {match.found_item?.description || "N/A"}
                </p>

                <p>
                  <strong>Date:</strong>{" "}
                  {match.found_item?.item_date || "N/A"}
                </p>

                <p>
                  <strong>Location:</strong>{" "}
                  {match.found_item?.location || "N/A"}
                </p>

                <p>
                  <strong>Match ID:</strong>{" "}
                  {match.match_id}
                </p>

                <p>
                  <strong>Matching score:</strong>{" "}
                  {Number(
                    match.similarity_score || 0
                  ).toFixed(1)}
                  %
                </p>
                <p className="match-explanation">
                  <strong>Why it was suggested:</strong>{" "}
                  Name {match.explanation?.components?.name ?? "N/A"}%, category {match.explanation?.category_match ? "matches" : "does not match"}, date proximity {match.explanation?.date_proximity_score ?? "N/A"}%.
                </p>
                {match.explanation?.conflicts?.length > 0 && <p className="match-conflicts"><strong>Conflicting details:</strong> {match.explanation.conflicts.join(" ")}</p>}
                {match.explanation?.missing_information?.length > 0 && <p className="match-missing">Missing comparison information: {match.explanation.missing_information.join(", ")}.</p>}

                <p><strong>Report status:</strong> {match.found_item?.status || "Unavailable"}</p>

                <div className="match-actions">
                  <button type="button" onClick={() => handleSubmitClaim(match.match_id)} disabled={submittingClaimId === match.match_id}>
                    {submittingClaimId === match.match_id ? "Submitting claim..." : "Submit claim"}
                  </button>
                  <button type="button" className="secondary-button compact-button" onClick={() => handleStartChat(match.match_id)} disabled={chatRequestingId === match.match_id}>
                    {chatRequestingId === match.match_id ? "Starting chat..." : "Start chat"}
                  </button>
                </div>
                <button type="button" className="secondary-button compact-button" onClick={() => handleResolve(match.match_id)}>Confirm handover completed</button>
              </div>
            ))}
          </div>
        )}

        {!matching &&
          lostItemId &&
          matches.length === 0 &&
          !error && (
            <div className="no-matches">
              <h2>No Matches Found</h2>

              <p>
                We could not find a matching found item
                right now. Check your claims later as
                new found items may be reported.
              </p>
            </div>
          )}
        {!matching && lostItemId && matches.length === 0 && <button type="button" className="secondary-button compact-button" onClick={refreshMatches}>Refresh possible matches</button>}
      </div>
    </div>
  );
}

export default LostItem;
