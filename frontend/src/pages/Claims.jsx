import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiUrl } from "../api";

const RESPONSE_ERROR = "We could not read the claims response. Please try again.";

async function readJson(response, fallback) {
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(RESPONSE_ERROR);
  }
  if (!response.ok) {
    throw new Error(data && typeof data === "object" && typeof data.detail === "string" ? data.detail : fallback);
  }
  return data;
}

function Claims() {
  const [claims, setClaims] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [updatingClaimId, setUpdatingClaimId] = useState(null);
  const [chatRequestingId, setChatRequestingId] = useState(null);
  const [message, setMessage] = useState("");

  async function loadClaims() {
    try {
      setLoading(true);
      setError("");

      const token = localStorage.getItem("goodfind_access_token");
      if (!token) {
        throw new Error("Please login to view your claims.");
      }
      const response = await fetch(apiUrl("/api/claims"), {
        headers: { Authorization: `Bearer ${token}` },
      });

      const data = await readJson(response, "Failed to load claims.");
      if (!Array.isArray(data.claims)) throw new Error(RESPONSE_ERROR);
      setClaims(data.claims);
    } catch (err) {
      setError(err.message || "Failed to load claims.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const timer = setTimeout(() => { void loadClaims(); }, 0);
    return () => clearTimeout(timer);
  }, []);

  async function updateClaim(claimId, status) {
    try {
      setUpdatingClaimId(claimId);
      setError("");
      setMessage("");

      const token = localStorage.getItem("goodfind_access_token");
      if (!token) {
        throw new Error("Please login before responding to a claim.");
      }

      const response = await fetch(
        apiUrl(`/api/claims/${claimId}`),
        {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            status,
          }),
        }
      );

      await readJson(response, "Failed to update claim.");

      setMessage(status === "ACCEPTED"
        ? "Claim accepted. The claimant can now start a private chat to coordinate a handover."
        : "Claim rejected successfully.");

      await loadClaims();
    } catch (err) {
      setError(err.message || "Failed to update claim.");
    } finally {
      setUpdatingClaimId(null);
    }
  }

  async function startChat(matchId, claimId) {
    try {
      setChatRequestingId(claimId);
      setError("");
      setMessage("");
      const token = localStorage.getItem("goodfind_access_token");
      if (!token) throw new Error("Please login before starting a private chat.");
      const response = await fetch(apiUrl("/api/chat/requests"), {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ match_id: matchId }),
      });
      await readJson(response, "Failed to start private chat.");
      setMessage("Private chat request sent. You can message after it is accepted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start private chat.");
    } finally {
      setChatRequestingId(null);
    }
  }

  function getStatusClass(status) {
    if (status === "ACCEPTED") {
      return "status accepted";
    }

    if (status === "REJECTED") {
      return "status rejected";
    }

    return "status pending";
  }

  return (
    <div className="report-page claims-page">
      <div className="report-container">
        <div className="claims-shell"
          style={{
            background: "#ffffff",
            borderRadius: "16px",
            padding: "30px",
            boxShadow: "0 4px 18px rgba(0,0,0,0.08)",
          }}
        >
          <div className="report-header">
            <p className="section-label"
              style={{
                margin: 0,
                fontSize: "13px",
                fontWeight: "700",
                letterSpacing: "1px",
                color: "#16805c",
              }}
            >
              CLAIM MANAGEMENT
            </p>

            <h1
              style={{
                margin: "8px 0",
                fontSize: "32px",
                color: "#1f2933",
              }}
            >
              My Claims
            </h1>

            <p
              style={{
                margin: 0,
                color: "#667085",
                lineHeight: "1.6",
              }}
            >
              View your item claims and respond to claims submitted
              for items you found.
            </p>
          </div>

          {loading && (
            <div
              style={{
                padding: "30px",
                textAlign: "center",
                color: "#667085",
              }}
            >
              Loading claims...
            </div>
          )}

          {!loading && error && (
            <div
              role="alert"
              style={{
                padding: "15px 18px",
                marginBottom: "20px",
                borderRadius: "10px",
                background: "#fff1f0",
                color: "#b42318",
                border: "1px solid #fecdca",
              }}
            >
              <p>{error}</p><button type="button" className="secondary-button compact-button" onClick={() => { void loadClaims(); }}>Try again</button>
            </div>
          )}

          {!loading && message && (
            <div
              role="status"
              style={{
                padding: "15px 18px",
                marginBottom: "20px",
                borderRadius: "10px",
                background: "#ecfdf3",
                color: "#027a48",
                border: "1px solid #abefc6",
              }}
            >
              {message}
            </div>
          )}

          {!loading && !error && claims.length === 0 && (
            <div
              style={{
                textAlign: "center",
                padding: "50px 20px",
                border: "1px dashed #d0d5dd",
                borderRadius: "12px",
              }}
            >
              <h2
                style={{
                  marginBottom: "10px",
                  color: "#344054",
                }}
              >
                No claims yet
              </h2>

              <p
                style={{
                  margin: 0,
                  color: "#667085",
                }}
              >
                Your submitted claims and incoming claims will
                appear here.
              </p>
            </div>
          )}

          {!loading && claims.length > 0 && (
            <div className="claim-list"
              style={{
                display: "grid",
                gap: "20px",
              }}
            >
              {claims.map((claim) => {
                const storedUser =
                  localStorage.getItem("goodfind_user");

                let currentUserId = null;

                try {
                  if (storedUser) {
                    currentUserId = JSON.parse(storedUser).user_id;
                  }
                } catch {
                  currentUserId = null;
                }

                const isClaimant =
                  Number(claim.claimant_user_id) ===
                  Number(currentUserId);

                const isFoundOwner =
                  Number(claim.found_item_owner_id) ===
                  Number(currentUserId);

                return (
                  <div className="claim-card"
                    key={claim.claim_id}
                    style={{
                      border: "1px solid #e4e7ec",
                      borderRadius: "14px",
                      padding: "22px",
                      background: "#ffffff",
                    }}
                  >
                    <div className="claim-card-header"
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "flex-start",
                        gap: "15px",
                        flexWrap: "wrap",
                      }}
                    >
                      <div>
                        <p
                          style={{
                            margin: "0 0 6px",
                            fontSize: "12px",
                            fontWeight: "700",
                            letterSpacing: "0.8px",
                            color: "#667085",
                          }}
                        >
                          CLAIM #{claim.claim_id}
                        </p>

                        <h2
                          style={{
                            margin: 0,
                            fontSize: "22px",
                            color: "#1f2933",
                          }}
                        >
                          {claim.lost_item?.item_name ||
                            "Lost Item"}
                        </h2>
                      </div>

                      <span
                        className={getStatusClass(claim.status)}
                        style={{
                          display: "inline-block",
                          padding: "7px 12px",
                          borderRadius: "20px",
                          fontSize: "12px",
                          fontWeight: "700",
                          background:
                            claim.status === "ACCEPTED"
                              ? "#ecfdf3"
                              : claim.status === "REJECTED"
                              ? "#fff1f0"
                              : "#fffaeb",
                          color:
                            claim.status === "ACCEPTED"
                              ? "#027a48"
                              : claim.status === "REJECTED"
                              ? "#b42318"
                              : "#b54708",
                        }}
                      >
                        {claim.status}
                      </span>
                    </div>

                    <div className="claim-items"
                      style={{
                        display: "grid",
                        gridTemplateColumns:
                          "repeat(auto-fit, minmax(220px, 1fr))",
                        gap: "15px",
                        marginTop: "20px",
                      }}
                    >
                      <div className="claim-item"
                        style={{
                          background: "#f8fafc",
                          padding: "15px",
                          borderRadius: "10px",
                        }}
                      >
                        <p
                          style={{
                            margin: "0 0 6px",
                            fontSize: "12px",
                            fontWeight: "700",
                            color: "#667085",
                          }}
                        >
                          LOST ITEM
                        </p>

                        <strong
                          style={{
                            color: "#344054",
                          }}
                        >
                          {claim.lost_item?.item_name ||
                            "Unknown"}
                        </strong>

                        <p
                          style={{
                            margin: "6px 0 0",
                            color: "#667085",
                          }}
                        >
                          Category:{" "}
                          {claim.lost_item?.category ||
                            "Not specified"}
                        </p>
                      </div>

                      <div className="claim-item"
                        style={{
                          background: "#f8fafc",
                          padding: "15px",
                          borderRadius: "10px",
                        }}
                      >
                        <p
                          style={{
                            margin: "0 0 6px",
                            fontSize: "12px",
                            fontWeight: "700",
                            color: "#667085",
                          }}
                        >
                          FOUND ITEM
                        </p>

                        <strong
                          style={{
                            color: "#344054",
                          }}
                        >
                          {claim.found_item?.item_name ||
                            "Unknown"}
                        </strong>

                        <p
                          style={{
                            margin: "6px 0 0",
                            color: "#667085",
                          }}
                        >
                          Category:{" "}
                          {claim.found_item?.category ||
                            "Not specified"}
                        </p>
                      </div>
                    </div>

                    <div className="claim-actions"
                      style={{
                        marginTop: "18px",
                        paddingTop: "18px",
                        borderTop: "1px solid #eaecf0",
                        color: "#667085",
                        fontSize: "14px",
                      }}
                    >
                      {isClaimant && (
                        <div>
                          <p style={{ margin: 0 }}><strong>You submitted this claim.</strong>{" "}{claim.status === "ACCEPTED" ? "Your claim was accepted. Start a private chat to arrange a safe handover." : claim.status === "REJECTED" ? "This claim was not accepted." : "The person who reported the found item can review it."}</p>
                          {claim.status === "ACCEPTED" && <div className="claim-action-buttons" style={{ marginTop: "14px" }}><button type="button" className="primary-button compact-button" onClick={() => startChat(claim.match_id, claim.claim_id)} disabled={chatRequestingId === claim.claim_id}>{chatRequestingId === claim.claim_id ? "Starting chat..." : "Start private chat"}</button><Link to="/messages" className="secondary-button compact-button">Open messages</Link></div>}
                        </div>
                      )}

                      {isFoundOwner && (
                        <div>
                          <p
                            style={{
                              margin: "0 0 14px",
                            }}
                          >
                            <strong>
                              Someone has claimed your found item.
                            </strong>
                            {" "}
                            Review the claim and decide whether to
                            accept or reject it.
                          </p>

                          {claim.status === "PENDING" && (
                            <div className="claim-action-buttons"
                              style={{
                                display: "flex",
                                gap: "10px",
                                flexWrap: "wrap",
                              }}
                            >
                              <button
                                type="button"
                                onClick={() =>
                                  updateClaim(
                                    claim.claim_id,
                                    "ACCEPTED"
                                  )
                                }
                                disabled={
                                  updatingClaimId ===
                                  claim.claim_id
                                }
                                style={{
                                  border: "none",
                                  borderRadius: "8px",
                                  padding: "11px 18px",
                                  background: "#16805c",
                                  color: "#ffffff",
                                  fontWeight: "700",
                                  cursor: "pointer",
                                }}
                              >
                                {updatingClaimId ===
                                claim.claim_id
                                  ? "Updating..."
                                  : "Accept Claim"}
                              </button>

                              <button
                                type="button"
                                onClick={() =>
                                  updateClaim(
                                    claim.claim_id,
                                    "REJECTED"
                                  )
                                }
                                disabled={
                                  updatingClaimId ===
                                  claim.claim_id
                                }
                                style={{
                                  border: "1px solid #d0d5dd",
                                  borderRadius: "8px",
                                  padding: "11px 18px",
                                  background: "#ffffff",
                                  color: "#b42318",
                                  fontWeight: "700",
                                  cursor: "pointer",
                                }}
                              >
                                Reject Claim
                              </button>
                            </div>
                          )}

                          {claim.status === "ACCEPTED" && (
                            <p
                              style={{
                                margin: 0,
                                color: "#027a48",
                                fontWeight: "600",
                              }}
                            >
                              You accepted this claim. The claimant can now request private chat to coordinate a handover.
                            </p>
                          )}

                          {claim.status === "REJECTED" && (
                            <p
                              style={{
                                margin: 0,
                                color: "#b42318",
                                fontWeight: "600",
                              }}
                            >
                              You rejected this claim.
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default Claims;
