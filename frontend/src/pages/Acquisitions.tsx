import { Link } from "react-router-dom";
import { PageHeader } from "../components/UI";
export default function Acquisitions() {
  return (
    <>
      <PageHeader
        title="Acquisitions"
        description="Introduce purchased, gifted or otherwise acquired biological material. This records outside origins without implying that you prepared or inoculated it."
      />
      <section className="panel workflow-source">
        <h2>Receive outside material</h2>
        <p>
          Register cultures, agar, LC containers and syringes, spores, spawn or
          ready-to-fruit material with supplier, origin and acquisition details.
        </p>
        <Link className="button primary" to="/acquisitions/receive">
          Receive Acquisition
        </Link>
        <p>
          Existing acquisitions and their source relationships remain available
          in <Link to="/culture-library">Culture Library</Link>.
        </p>
      </section>
    </>
  );
}
