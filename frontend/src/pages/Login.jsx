import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { apiUrl } from "../api";

function Login() {
  const navigate = useNavigate();

  const [formData, setFormData] = useState({
    email: "",
    password: "",
  });

  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  function handleChange(event) {
    const { name, value } = event.target;

    setFormData((previous) => ({
      ...previous,
      [name]: value,
    }));
  }

  async function handleSubmit(event) {
    event.preventDefault();

    setMessage("");
    setError("");
    setLoading(true);

    try {
      const response = await fetch(
        apiUrl("/api/auth/login"),
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(formData),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Login failed");
      }

      localStorage.setItem("goodfind_user", JSON.stringify(data.user));
      localStorage.setItem("goodfind_access_token", data.access_token);

      setMessage("Login successful!");

      setTimeout(() => {
        navigate("/");
      }, 800);
    } catch (error) {
      setError(error.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="report-page">
      <div className="report-container">
        <div className="report-header">
          <p className="section-label">WELCOME BACK</p>

          <h1>Login to GoodFind</h1>

          <p>
            Sign in to report lost items, report found items, and manage
            your GoodFind activity.
          </p>
        </div>

        <form className="report-form" onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="email">Email</label>

            <input
              id="email"
              name="email"
              type="email"
              placeholder="Enter your email"
              value={formData.email}
              onChange={handleChange}
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <div className="password-field"><input id="password" name="password" type={showPassword ? "text" : "password"} placeholder="Enter your password" value={formData.password} onChange={handleChange} required /><button type="button" className="password-toggle" onClick={() => setShowPassword((current) => !current)} aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? "Hide" : "Show"}</button></div>
          </div>

          {message && <p className="success-message" role="status">{message}</p>}

          {error && <p className="error-message" role="alert">{error}</p>}

          <button
            type="submit"
            className="primary-button submit-button"
            disabled={loading}
          >
            {loading ? "Logging in..." : "Login"}
          </button>

          <p className="auth-footer">
            Don't have an account?{" "}
            <Link to="/register">Create an account</Link>
          </p>
        </form>
      </div>
    </div>
  );
}

export default Login;
