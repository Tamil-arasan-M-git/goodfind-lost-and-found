import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiUrl } from "../api";

function FoundItems() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [claimingItemId, setClaimingItemId] = useState(null);
  const [claimFeedback, setClaimFeedback] = useState({});
  const [filters, setFilters] = useState({ search: "", category: "", location: "" });

  useEffect(() => {
    async function loadFoundItems() {
      try {
        const params = new URLSearchParams(Object.entries(filters).filter(([, value]) => value));
        const response = await fetch(apiUrl(`/api/items/found?${params}`));

        const data = await response.json();

        if (!response.ok) {
          throw new Error(
            data.detail || "Failed to load found items"
          );
        }

        setItems(data.items || []);
      } catch (error) {
        setError(error.message);
      } finally {
        setLoading(false);
      }
    }

    loadFoundItems();
  }, [filters]);

  async function submitClaim(foundItemId) {
    const token = localStorage.getItem("goodfind_access_token");
    if (!token) {
      setClaimFeedback((current) => ({ ...current, [foundItemId]: "Please log in to claim a possible match." }));
      return;
    }
    setClaimingItemId(foundItemId);
    setClaimFeedback((current) => ({ ...current, [foundItemId]: "" }));
    try {
      const response = await fetch(apiUrl(`/api/claims/found/${foundItemId}`), {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      let data = {};
      try {
        data = await response.json();
      } catch {
        throw new Error("We could not read the claim response. Please try again.");
      }
      if (!response.ok) throw new Error(data.detail || "Failed to submit claim.");
      setClaimFeedback((current) => ({
        ...current,
        [foundItemId]: data.already_pending
          ? "Your claim is already pending review."
          : "Claim submitted. The found-item reporter can review it in Claims.",
      }));
    } catch (claimError) {
      setClaimFeedback((current) => ({ ...current, [foundItemId]: claimError.message || "Failed to submit claim." }));
    } finally {
      setClaimingItemId(null);
    }
  }

  return (
    <div className="report-page">
      <div className="report-container">

        <div className="report-header">
          <p className="section-label">
            FOUND ITEMS
          </p>

          <h1>
            Items reported as found
          </h1>

          <p>
            Browse items that people have found and reported
            through GoodFind.
          </p>
        </div>

        <div className="report-form listing-toolbar">
          <div className="form-row">
            <div className="form-group"><label htmlFor="found-search">Search</label><input id="found-search" value={filters.search} onChange={(event) => setFilters({ ...filters, search: event.target.value })} placeholder="Name or description" /></div>
            <div className="form-group"><label htmlFor="found-category">Category</label><input id="found-category" value={filters.category} onChange={(event) => setFilters({ ...filters, category: event.target.value })} placeholder="Accessories" /></div>
          </div>
          <div className="form-group"><label htmlFor="found-location">Location</label><input id="found-location" value={filters.location} onChange={(event) => setFilters({ ...filters, location: event.target.value })} placeholder="Library" /></div>
          <button type="button" className="secondary-button" onClick={() => setFilters({ search: "", category: "", location: "" })}>Clear filters</button>
        </div>

        {loading && <p className="loading-state" role="status">Loading found items...</p>}

        {error && <p className="error-message" role="alert">{error}</p>}

        {!loading && !error && items.length === 0 && (
          <div className="empty-state">

            <h3>
              No found items reported yet.
            </h3>

            <p className="listing-count">
              Be the first person to report a found item.
            </p>

            <Link
              to="/report/found"
              className="primary-button"
            >
              Report Found Item
            </Link>

          </div>
        )}

        {!loading && !error && items.length > 0 && (
          <div>

            <p>
              {items.length} found item
              {items.length !== 1 ? "s" : ""} reported
            </p>

            <div className="item-grid">{items.map((item) => (
              <article key={item.item_id} className="item-card">

                <span className="badge badge-found">FOUND ITEM</span>

                <h2>
                  {item.item_name}
                </h2>

                <p>
                  <strong>Category:</strong>{" "}
                  {item.category}
                </p>

                <p>
                  <strong>Description:</strong>{" "}
                  {item.description || "No description provided"}
                </p>

                <p>
                  <strong>Date Found:</strong>{" "}
                  {item.item_date}
                </p>

                <p>
                  <strong>Location:</strong>{" "}
                  {item.location}
                </p>

                <span className="status pending">{item.status}</span>

                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => submitClaim(item.item_id)}
                  disabled={claimingItemId === item.item_id}
                >
                  {claimingItemId === item.item_id ? "Submitting claim..." : "I Lost Something Similar"}
                </button>
                {claimFeedback[item.item_id] && <p className="claim-feedback" role="status">{claimFeedback[item.item_id]}</p>}

              </article>
            ))}</div>

          </div>
        )}

      </div>
    </div>
  );
}

export default FoundItems;
