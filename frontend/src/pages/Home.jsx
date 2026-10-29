import { Link, useNavigate } from "react-router-dom";
import heroImage from "../assets/goodfind-backpack.svg";

function Home() {
  const navigate = useNavigate();

  function handleReport(type) {
    const storedUser = localStorage.getItem("goodfind_user");

    if (!storedUser) {
      navigate("/login", {
        state: {
          from: `/report/${type}`,
        },
      });

      return;
    }

    navigate(`/report/${type}`);
  }

  return (
    <div className="home-page">

      {/* Hero Section */}
      <section className="hero" id="home">

        <div className="hero-content">

          <p className="eyebrow"><span aria-hidden="true">✦</span> A safer way to reconnect</p>

          <h1>
            A good turn can bring
            <br /><span>something home.</span>
          </h1>

          <p className="hero-description">
            Report an item, discover thoughtful matches, and arrange a return in a private space built to protect everyone involved.
          </p>

          <div className="hero-buttons">

            <button
              type="button"
              className="primary-button"
              onClick={() => handleReport("lost")}
            >
              Report Lost Item
            </button>

            <button
              type="button"
              className="secondary-button"
              onClick={() => handleReport("found")}
            >
              Report Found Item
            </button>

            <Link to="/lost-items" className="text-link-button">
              Explore community reports <span aria-hidden="true">→</span>
            </Link>

          </div>
        </div>

        <div className="hero-art-card">
          <div className="hero-art-glow" aria-hidden="true" />
          <img src={heroImage} alt="A backpack waiting to be reunited with its owner" />
          <div className="hero-art-caption"><span className="hero-art-dot" aria-hidden="true" /> <span>Small items. Big stories.</span></div>
        </div>

      </section>

      {/* How It Works */}
      <section
        className="how-section"
        id="how-it-works"
      >

        <div className="section-heading">

          <p className="eyebrow">HOW IT WORKS</p>

          <h2>
            A calmer way to recover what matters
          </h2>

        </div>

        <div className="steps">

          <div className="step-card">

            <div className="step-number">
              01
            </div>

            <h3>
              Report
            </h3>

            <p>
              Report a lost or found item with its
              important details.
            </p>

          </div>

          <div className="step-card">

            <div className="step-number">
              02
            </div>

            <h3>
              Match
            </h3>

            <p>
              Our matching system surfaces potential reports worth reviewing. It does not confirm ownership on its own.
            </p>

          </div>

          <div className="step-card">

            <div className="step-number">
              03
            </div>

            <h3>
              Verify
            </h3>

            <p>
              Users verify the ownership details before
              arranging a handover.
            </p>

          </div>

          <div className="step-card">

            <div className="step-number">
              04
            </div>

            <h3>
              Return
            </h3>

            <p>
              Arrange a safe handover and mark the item
              as recovered.
            </p>

          </div>

        </div>

      </section>

      {/* About */}
      <section className="about-section" id="about">

        <div>

          <p className="eyebrow">ABOUT GOODFIND</p>

          <h2>
            A smarter way to reconnect people with
            their belongings.
          </h2>

        </div>

        <div className="about-copy"><p>GoodFind makes the ordinary kindness of returning an item easier to act on. Listings stay focused on the item, while private messages use aliases by default.</p><Link to="/found-items" className="inline-link">Browse community reports <span aria-hidden="true">→</span></Link></div>

      </section>

      {/* Footer */}
      <footer className="footer">

        <div className="logo">
          <span className="logo-mark" aria-hidden="true">♥</span><span>GoodFind</span>
        </div>

        <p>
          Thoughtful tools for everyday good turns.
        </p>

        <p className="copyright">
          © 2026 GoodFind. All rights reserved.
        </p>

      </footer>

    </div>
  );
}

export default Home;
