import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apiUrl } from "../api";
import { REPORT_CATEGORY_OPTIONS } from "../reportForm";

const INITIAL_FILTERS = { search: "", category: "", location: "", status: "" };
const RESPONSE_ERROR = "We could not read the listings response. Please try again.";

function isPaginationValue(value, minimum) {
  return Number.isInteger(value) && value >= minimum;
}

async function readListingResponse(response, type) {
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error(RESPONSE_ERROR);
  }

  if (!response.ok) {
    const detail = payload && typeof payload === "object" && typeof payload.detail === "string"
      ? payload.detail
      : `Failed to load ${type} items`;
    throw new Error(detail);
  }

  if (!payload || typeof payload !== "object" || Array.isArray(payload)
    || !Array.isArray(payload.items)
    || !isPaginationValue(payload.total, 0)
    || !isPaginationValue(payload.page, 1)
    || !isPaginationValue(payload.page_size, 1)) {
    throw new Error(RESPONSE_ERROR);
  }

  return payload;
}

function formatDate(value) {
  if (!value) return "Date unavailable";
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function ItemListing({ type }) {
  const isLost = type === "lost";
  const label = isLost ? "LOST" : "FOUND";
  const [filters, setFilters] = useState(INITIAL_FILTERS);
  const [items, setItems] = useState([]);
  const [page, setPage] = useState(1);
  const [pageInfo, setPageInfo] = useState({ total: 0, page: 1, pageSize: 20 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [expandedItemId, setExpandedItemId] = useState(null);
  const [claimingItemId, setClaimingItemId] = useState(null);
  const [claimFeedback, setClaimFeedback] = useState({});
  const [failedImageIds, setFailedImageIds] = useState(() => new Set());
  const activeFilters = useMemo(() => Object.entries(filters).filter(([, value]) => value.trim()), [filters]);

  function updateFilter(field, value) {
    setFilters((current) => ({ ...current, [field]: value }));
    setPage(1);
  }

  function resetFilters() {
    setFilters(INITIAL_FILTERS);
    setPage(1);
  }

  function toggleDetails(itemId) {
    setExpandedItemId((current) => current === itemId ? null : itemId);
  }

  function markImageUnavailable(itemId) {
    setFailedImageIds((current) => new Set(current).add(itemId));
  }

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

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true);
      setError("");
      const params = new URLSearchParams({ page: String(page), page_size: "20" });
      activeFilters.forEach(([key, value]) => params.set(key, value.trim()));
      try {
        const response = await fetch(apiUrl(`/api/items/${type}?${params}`), { signal: controller.signal });
        const data = await readListingResponse(response, type);
        if (!controller.signal.aborted) {
          setItems(data.items);
          setPageInfo({ total: data.total, page: data.page, pageSize: data.page_size });
        }
      } catch (requestError) {
        if (requestError.name !== "AbortError" && !controller.signal.aborted) {
          setItems([]);
          setError(requestError instanceof Error ? requestError.message : RESPONSE_ERROR);
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 220);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [activeFilters, page, reloadKey, type]);

  const totalPages = Math.max(1, Math.ceil(pageInfo.total / pageInfo.pageSize));
  const hasFilters = activeFilters.length > 0;
  const reportAction = isLost ? "Report lost item" : "Report found item";
  const alternateAction = isLost ? "Explore found items" : "Explore lost items";
  const alternatePath = isLost ? "/found-items" : "/lost-items";

  return (
    <main className="report-page listing-page">
      <div className="report-container listing-container">
        <header className="listing-hero">
          <div>
            <p className="section-label">{label} ITEMS</p>
            <h1>{isLost ? "Explore lost items" : "Explore found items"}</h1>
            <p>{isLost ? "Browse reports from people looking for something important. A found report could be the lead that helps return it." : "Browse items reported as found and help reconnect them with the people who may be looking for them."}</p>
          </div>
          <div className="listing-hero-actions">
            <Link to={`/report/${type}`} className="primary-button">{reportAction}</Link>
            <Link to={alternatePath} className="secondary-button">{alternateAction}</Link>
          </div>
        </header>

        <section className="listing-search-panel" aria-label={`${label.toLowerCase()} item filters`}>
          <div className="listing-search-heading"><div><p className="listing-kicker">SEARCH REPORTS</p><h2>Find an item report</h2></div>{hasFilters && <p className="active-filter-summary" aria-live="polite">{activeFilters.length} filter{activeFilters.length === 1 ? "" : "s"} active</p>}</div>
          <div className="listing-filter-grid">
            <div className="form-group listing-search-field"><label htmlFor={`${type}-search`}>Search reports</label><div className="search-input-wrap"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="m21 21-4.35-4.35m2.35-5.15a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0Z" /></svg><input id={`${type}-search`} value={filters.search} onChange={(event) => updateFilter("search", event.target.value)} placeholder="Search wallets, bags, keys…" /></div></div>
            <div className="form-group"><label htmlFor={`${type}-category`}>Category</label><select id={`${type}-category`} value={filters.category} onChange={(event) => updateFilter("category", event.target.value)}><option value="">All categories</option>{REPORT_CATEGORY_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></div>
            <div className="form-group"><label htmlFor={`${type}-location`}>Location</label><input id={`${type}-location`} value={filters.location} onChange={(event) => updateFilter("location", event.target.value)} placeholder="Enter a location" /></div>
            <div className="form-group"><label htmlFor={`${type}-status`}>Status</label><select id={`${type}-status`} value={filters.status} onChange={(event) => updateFilter("status", event.target.value)}><option value="">Any status</option><option value="ACTIVE">Active</option><option value="HANDOVER_IN_PROGRESS">Handover in progress</option><option value="RESOLVED">Resolved</option><option value="CLOSED">Closed</option></select></div>
          </div>
          <div className="listing-filter-actions"><p>Searches item names and descriptions. Filters work together.</p><button type="button" className="text-link-button" onClick={resetFilters} disabled={!hasFilters}>Clear filters</button></div>
        </section>

        <aside className="listing-privacy-note"><span aria-hidden="true">⌁</span><p><strong>Protect your privacy.</strong> Avoid sharing phone numbers, email addresses or personal identifiers in public reports.</p></aside>

        {loading && <section className="listing-results" aria-live="polite" aria-busy="true"><div className="listing-results-heading"><div><p className="listing-kicker">COMMUNITY REPORTS</p><h2>Loading reports</h2></div></div><div className="item-grid skeleton-grid">{Array.from({ length: 6 }, (_, index) => <div className="item-card item-skeleton" key={index} aria-hidden="true"><div className="skeleton-image" /><div className="skeleton-line short" /><div className="skeleton-line" /><div className="skeleton-line medium" /></div>)}</div></section>}
        {!loading && error && <div className="error-state" role="alert"><div><strong>We couldn’t load these reports.</strong><p>{error}</p></div><button type="button" className="secondary-button" onClick={() => setReloadKey((key) => key + 1)}>Try again</button></div>}
        {!loading && !error && items.length === 0 && <div className="empty-state"><p className="listing-kicker">{hasFilters ? "NO RESULTS" : "COMMUNITY REPORTS"}</p><h2>{hasFilters ? "No items match these filters." : `No ${type} items reported yet.`}</h2><p>{hasFilters ? "Clear a filter or try another search term to broaden your results." : `Help the community by being the first to report a ${type} item.`}</p><div className="empty-state-actions">{hasFilters && <button type="button" className="secondary-button" onClick={resetFilters}>Clear filters</button>}<Link to={`/report/${type}`} className="primary-button">{reportAction}</Link></div></div>}

        {!loading && !error && items.length > 0 && <>
          <section className="listing-results" aria-label={`${label.toLowerCase()} item results`}><div className="listing-results-heading"><div><p className="listing-kicker">COMMUNITY REPORTS</p><h2>Browse recent reports</h2></div><p className="listing-count" aria-live="polite">Showing {items.length} of {pageInfo.total} {type} report{pageInfo.total === 1 ? "" : "s"}</p></div>
          <div className="item-grid">{items.map((item) => <article key={item.item_id} className="item-card listing-item-card">
            {item.image_url && !failedImageIds.has(item.item_id) ? <img className="listing-image" src={apiUrl(item.image_url)} alt={`Photo of ${item.item_name || `${type} item`}`} onError={() => markImageUnavailable(item.item_id)} /> : <div className="listing-image listing-image-placeholder" aria-label="No image provided"><span aria-hidden="true">⌑</span><span>No photo provided</span></div>}
            <div className="listing-card-topline"><span className={`badge ${isLost ? "badge-lost" : "badge-found"}`}>{label} ITEM</span><span className={`status ${String(item.status || "ACTIVE").toLowerCase().replaceAll("_", "-")}`}>{String(item.status || "ACTIVE").replaceAll("_", " ")}</span></div>
            <h3>{item.item_name || "Unnamed item"}</h3>
            <p className="listing-category">{item.category || "Not specified"}</p>
            <dl className="item-meta"><div><dt>{isLost ? "Lost" : "Found"}</dt><dd>{formatDate(item.item_date)}</dd></div><div><dt>Location</dt><dd>{item.location || "Not specified"}</dd></div></dl>
            {expandedItemId === item.item_id && <div className="listing-details" id={`item-details-${item.item_id}`}><p><strong>Description</strong>{item.description || "No description provided"}</p></div>}
            <div className="listing-card-actions"><button type="button" className="text-link-button" aria-expanded={expandedItemId === item.item_id} aria-controls={`item-details-${item.item_id}`} onClick={() => toggleDetails(item.item_id)}>{expandedItemId === item.item_id ? "Hide details" : "View details"}</button>{isLost ? <Link to="/report/found" className="secondary-button compact-button">I found something similar</Link> : <button type="button" className="secondary-button compact-button" onClick={() => submitClaim(item.item_id)} disabled={claimingItemId === item.item_id}>{claimingItemId === item.item_id ? "Submitting claim..." : "I lost something similar"}</button>}</div>
            {!isLost && claimFeedback[item.item_id] && <p className="claim-feedback" role="status">{claimFeedback[item.item_id]}</p>}
          </article>)}</div>
          {totalPages > 1 && <nav className="pagination" aria-label="Listing pages"><button className="secondary-button compact-button" type="button" disabled={page <= 1} onClick={() => setPage((current) => current - 1)}>Previous</button><span>Page {pageInfo.page} of {totalPages}</span><button className="secondary-button compact-button" type="button" disabled={page >= totalPages} onClick={() => setPage((current) => current + 1)}>Next</button></nav>}
          </section>
        </>}
      </div>
    </main>
  );
}

export default ItemListing;
