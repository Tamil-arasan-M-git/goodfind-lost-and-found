import { Link, NavLink, useNavigate } from "react-router-dom";
import { useState } from "react";

function SiteHeader() {
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const storedUser = localStorage.getItem("goodfind_user");
  let user = null;

  try {
    user = storedUser ? JSON.parse(storedUser) : null;
  } catch {
    localStorage.removeItem("goodfind_user");
  }

  function logout() {
    localStorage.removeItem("goodfind_user");
    localStorage.removeItem("goodfind_access_token");
    setMenuOpen(false);
    navigate("/");
  }

  return (
    <header className="site-header">
      <nav className="navbar" aria-label="Main navigation">
        <Link className="logo" to="/" onClick={() => setMenuOpen(false)}>
          <span className="logo-mark" aria-hidden="true">♥</span><span>GoodFind</span>
        </Link>
        <button className="menu-toggle" type="button" aria-expanded={menuOpen} aria-label="Toggle navigation" onClick={() => setMenuOpen((open) => !open)}>
          <span /><span /><span />
        </button>
        <div className={`nav-links ${menuOpen ? "is-open" : ""}`}>
          <NavLink to="/lost-items" onClick={() => setMenuOpen(false)}>Browse items</NavLink>
          <a href="/#how-it-works" onClick={() => setMenuOpen(false)}>How it works</a>
          <a href="/#about" onClick={() => setMenuOpen(false)}>About</a>
          {user ? <>
            <NavLink to="/claims" onClick={() => setMenuOpen(false)}>Claims</NavLink>
            <NavLink to="/messages" onClick={() => setMenuOpen(false)}>Messages</NavLink>
            <span className="user-greeting">Hi, {user.name?.split(" ")[0] || "there"}</span>
            <button className="text-button" type="button" onClick={logout}>Log out</button>
          </> : <>
            <NavLink to="/login" onClick={() => setMenuOpen(false)}>Log in</NavLink>
            <NavLink className="nav-cta" to="/register" onClick={() => setMenuOpen(false)}>Create account</NavLink>
          </>}
        </div>
      </nav>
    </header>
  );
}

export default SiteHeader;
