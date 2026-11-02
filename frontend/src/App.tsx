import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AcquisitionForm, GrowForm } from "./pages/Provenance";
import {
  StockPage,
  PreparedPage,
  PreparedDetail,
  TransactionsPage,
} from "./pages/PreparationInventory";
import Inventory from "./pages/Inventory";
import {
  RecipesHome,
  RecipeList,
  RecipeDetail,
  RecipeEditor,
  recipeCategories,
} from "./pages/Recipes";
import Growing from "./pages/Growing";
import LegacyInoculation from "./pages/LegacyInoculation";
import PrepareMaterials from "./pages/PrepareMaterials";
import QuickCreatePage from "./pages/QuickCreate";
import Shell from "./components/Shell";
import Dashboard from "./pages/Dashboard";
import ModulePage, { modules } from "./pages/ModulePage";
import Settings from "./pages/Settings";
import { CultureLibrary, RecordDetail } from "./pages/CultureLibrary";
import { ReceiveForm, StrainForm } from "./pages/LibraryForms";
function LegacyRedirect({ to }: { to: string }) {
  const { search, hash } = useLocation();
  return <Navigate replace to={{ pathname: to, search, hash }} />;
}
export default function App() {
  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<Dashboard />} />
          <Route path="quick-create/:operation" element={<QuickCreatePage />} />
          <Route path="inventory" element={<Inventory />} />
          <Route path="inventory/stock" element={<StockPage />} />
          <Route path="recipes" element={<RecipesHome />} />
          {Object.keys(recipeCategories).map((category) => (
            <Route
              key={category}
              path={`recipes/${category}`}
              element={
                <RecipeList
                  category={category as keyof typeof recipeCategories}
                />
              }
            />
          ))}
          {Object.keys(recipeCategories).map((category) => (
            <Route
              key={category}
              path={`recipes/${category}/new`}
              element={
                <RecipeEditor
                  category={category as keyof typeof recipeCategories}
                />
              }
            />
          ))}
          <Route path="recipes/detail/:code" element={<RecipeDetail />} />
          <Route path="recipes/detail/:code/edit" element={<RecipeEditor />} />
          <Route
            path="laboratory"
            element={<Growing workspace="laboratory" />}
          />
          <Route
            path="cultivation"
            element={<Growing workspace="cultivation" />}
          />
          <Route
            path="inventory/prepared/inoculate"
            element={<LegacyInoculation />}
          />
          <Route
            path="inventory/recipes"
            element={<LegacyRedirect to="/recipes" />}
          />
          <Route
            path="inventory/prepared/prepare"
            element={<PrepareMaterials />}
          />
          <Route path="inventory/prepared" element={<PreparedPage />} />
          <Route path="inventory/prepared/:code" element={<PreparedDetail />} />
          <Route path="inventory/transactions" element={<TransactionsPage />} />
          <Route
            path="inventory/receive-acquisition"
            element={<AcquisitionForm />}
          />
          <Route path="inventory/strains/new" element={<StrainForm />} />
          <Route path="inventory/receive-culture" element={<ReceiveForm />} />
          <Route
            path="inventory/receive-spores"
            element={<ReceiveForm spores />}
          />
          <Route path="cultivation/register-grow" element={<GrowForm />} />
          <Route path="culture-library" element={<CultureLibrary />} />
          {Object.entries({
            acquire: "/inventory/receive-acquisition",
            "add-strain": "/inventory/strains/new",
            "receive-culture": "/inventory/receive-culture",
            "receive-spores": "/inventory/receive-spores",
            "register-grow": "/cultivation/register-grow",
          }).map(([legacy, to]) => (
            <Route
              key={legacy}
              path={`culture-library/${legacy}`}
              element={<LegacyRedirect to={to} />}
            />
          ))}
          <Route
            path="culture-library/:kind/:code"
            element={<RecordDetail />}
          />
          {(Object.keys(modules) as (keyof typeof modules)[])
            .filter(
              (module) =>
                !["inventory", "laboratory", "cultivation"].includes(module),
            )
            .map((module) => (
              <Route
                key={module}
                path={module}
                element={<ModulePage module={module} />}
              />
            ))}
          <Route path="settings" element={<Settings />} />
          <Route
            path="*"
            element={
              <div className="empty-state">
                <h1>Workspace not found</h1>
                <Link to="/">Return to Dashboard</Link>
              </div>
            }
          />
        </Route>
      </Routes>
    </>
  );
}
