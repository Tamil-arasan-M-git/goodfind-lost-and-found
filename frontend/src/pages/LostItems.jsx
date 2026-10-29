import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiUrl } from "../api";

function LostItems() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filters, setFilters] = useState({ search: "", category: "", location: "" });

  useEffect(() => {
    async function loadLostItems() {
      try {
        const params = new URLSearchParams(Object.entries(filters).filter(([, value]) => value));
        const response = await fetch(apiUrl(`/api/items/lost?${params}`));

        const data = await response.json();

        if (!response.ok) {
          throw new Error(
            data.detail || "Failed to load lost items"
          );
        }

        setItems(data.items || []);
      } catch (error) {
        setError(error.message);
      } finally {
        setLoading(false);
      }
    }

    loadLostItems();
  }, [filters]);

  return (
    <div className="report-page">
      <div className="report-container">

        <div className="report-header">
          <p className="section-label">
            LOST ITEMS
          </p>

          <h1>
            Items reported as lost
          </h1>

          <p>
            Browse items that people have reported missing.
            A matching found item may help return them to their owners.
          </p>
        </div>

        <div className="report-form listing-toolbar">
          <div className="form-row">
            <div className="form-group"><label htmlFor="lost-search">Search</label><input id="lost-search" value={filters.search} onChange={(event) => setFilters({ ...filters, search: event.target.value })} placeholder="Name or description" /></div>
            <div className="form-group"><label htmlFor="lost-category">Category</label><input id="lost-category" value={filters.category} onChange={(event) => setFilters({ ...filters, category: event.target.value })} placeholder="Accessories" /></div>
          </div>
          <div className="form-group"><label htmlFor="lost-location">Location</label><input id="lost-location" value={filters.location} onChange={(event) => setFilters({ ...filters, location: event.target.value })} placeholder="Library" /></div>
          <button type="button" className="secondary-button" onClick={() => setFilters({ search: "", category: "", location: "" })}>Clear filters</button>
        </div>

        {loading && <p className="loading-state" role="status">Loading lost items...</p>}

        {error && <p className="error-message" role="alert">{error}</p>}

        {!loading && !error && items.length === 0 && (
          <div className="empty-state">
            <h3>
              No lost items reported yet.
            </h3>

            <p className="listing-count">
              Be the first person to report a lost item.
            </p>

            <Link
              to="/report/lost"
              className="primary-button"
            >
              Report Lost Item
            </Link>
          </div>
        )}

        {!loading && !error && items.length > 0 && (
          <div>

            <p>
              {items.length} lost item
              {items.length !== 1 ? "s" : ""} reported
            </p>

            <div className="item-grid">{items.map((item) => (
              <article key={item.item_id} className="item-card">

                <span className="badge badge-lost">LOST ITEM</span>

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
                  <strong>Date Lost:</strong>{" "}
                  {item.item_date}
                </p>

                <p>
                  <strong>Location:</strong>{" "}
                  {item.location}
                </p>

                <span className="status pending">{item.status}</span>

                <Link
                  to={`/report/lost`}
                  className="secondary-button"
                >
                  Report a Similar Lost Item
                </Link>

              </article>
            ))}</div>

          </div>
        )}

      </div>
    </div>
  );
}

export default LostItems;
