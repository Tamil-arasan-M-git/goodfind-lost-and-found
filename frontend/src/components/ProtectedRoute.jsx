import { Navigate, useLocation } from "react-router-dom";

function ProtectedRoute({ children }) {
  const location = useLocation();

  const storedUser = localStorage.getItem("goodfind_user");

  if (!storedUser || !localStorage.getItem("goodfind_access_token")) {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: location.pathname }}
      />
    );
  }

  try {
    JSON.parse(storedUser);
  } catch {
    localStorage.removeItem("goodfind_user");
    localStorage.removeItem("goodfind_access_token");

    return (
      <Navigate
        to="/login"
        replace
        state={{ from: location.pathname }}
      />
    );
  }

  return children;
}

export default ProtectedRoute;
