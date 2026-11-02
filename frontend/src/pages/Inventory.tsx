import { Link } from "react-router-dom";
import { PackagePlus, Dna, Boxes } from "lucide-react";
import { InventoryNav } from "./PreparationInventory";
import { PageHeader, Panel } from "../components/UI";
export default function Inventory() {
  return (
    <>
      <InventoryNav />
      <PageHeader
        title="Inventory"
        description="Outside acquisitions, stock, reusable pools, recipes, prepared materials, and transaction history. Purchase tracking is planned."
      />
      <Panel
        title="Receive outside material"
        icon={PackagePlus}
        label="ACQUISITIONS"
      >
        <div className="workflow-source">
          <p>
            Register purchased, gifted, or otherwise acquired cultures, spores,
            spawn, or ready-to-fruit material. Start at the stage you received
            it; earlier history stays unknown.
          </p>
          <Link className="button primary" to="/inventory/receive-acquisition">
            Receive Acquisition
          </Link>
          <p>
            For preparation, inoculation, or transfers within your collection,
            use Dashboard Quick Create. Acquisition is not a substitute for
            those operations.
          </p>
        </div>
      </Panel>
      <Panel title="Strain management" icon={Dna}>
        <div className="workflow-source">
          <p>Manage reference identities without creating physical material.</p>
          <Link className="button" to="/inventory/strains/new">
            Add Strain
          </Link>
          <Link className="button" to="/culture-library">
            Browse catalog
          </Link>
        </div>
      </Panel>
      <Panel
        title="Preparation & Inventory"
        icon={Boxes}
        label="TRANSACTIONAL STOCK"
      >
        <div className="workflow-source">
          <p>
            Configure confirmed stock or unknown balances. Reserve reusable
            containers and prepare materials before inoculation; all deductions
            and adjustments are audited.
          </p>
          <div className="actions">
            <Link className="button" to="/inventory/stock">
              Stock & Pools
            </Link>
            <Link className="button" to="/inventory/recipes">
              Recipes
            </Link>
            <Link className="button" to="/inventory/prepared">
              Prepared Materials
            </Link>
            <Link className="button" to="/inventory/transactions">
              Transaction History
            </Link>
          </div>
        </div>
      </Panel>
    </>
  );
}
