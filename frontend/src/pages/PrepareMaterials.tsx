import { PageHeader } from "../components/UI";
import { InventoryNav } from "./PreparationInventory";
import { PreparationForm } from "./PreparationWorkflow";
export default function PrepareMaterials() {
  return (
    <>
      <InventoryNav />
      <PageHeader
        title="Prepare Materials"
        description="Save completed preparation and sterilization here. New materials are immediately Ready to Inoculate; choose their culture source later in Quick Create."
      />
      <PreparationForm />
    </>
  );
}
