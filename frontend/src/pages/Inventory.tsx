import { Link } from "react-router-dom";
import { StockPage } from "./PreparationInventory";
export default function Inventory() {
  return (
    <>
      <div className="actions">
        <Link className="button primary" to="/inventory/receive-acquisition">
          Receive Acquisition
        </Link>
        <Link className="button" to="/inventory/strains/new">
          Add Strain
        </Link>
      </div>
      <p>
        Receive outside culture material here, or keep optional ingredients and
        supplies below. Use Quick Create to record inoculated cultures directly.
      </p>
      <StockPage title="Inventory" />
    </>
  );
}
