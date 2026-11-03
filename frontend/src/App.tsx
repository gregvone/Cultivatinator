import {
  Link,
  Navigate,
  Route,
  Routes,
  useLocation,
  useParams,
} from "react-router-dom";
import { AcquisitionForm, GrowForm } from "./pages/Provenance";
import {
  PreparedPage,
  PreparedDetail,
  TransactionsPage,
} from "./pages/PreparationInventory";
import Acquisitions from "./pages/Acquisitions";
import {
  RecipesHome,
  LCMediaPage,
  RecipeList,
  RecipeDetail,
  RecipeEditor,
  recipeCategories,
} from "./pages/Recipes";
import Growing from "./pages/Growing";
import LegacyInoculation from "./pages/LegacyInoculation";
import QuickCreatePage from "./pages/QuickCreate";
import Shell from "./components/Shell";
import Dashboard from "./pages/Dashboard";
import Reports from "./pages/Reports";
import Settings from "./pages/Settings";
import { CultureLibrary, RecordDetail } from "./pages/CultureLibrary";
import { ReceiveForm, StrainForm } from "./pages/LibraryForms";
function LegacyRedirect({ to }: { to: string }) {
  const { search, hash } = useLocation();
  return <Navigate replace to={{ pathname: to, search, hash }} />;
}
function OldMaterialRedirect() {
  const { code } = useParams();
  return <LegacyRedirect to={`/history/materials/${code}`} />;
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
          <Route path="acquisitions" element={<Acquisitions />} />
          <Route path="acquisitions/receive" element={<AcquisitionForm />} />
          <Route
            path="acquisitions/receive-culture"
            element={<ReceiveForm />}
          />
          <Route
            path="acquisitions/receive-spores"
            element={<ReceiveForm spores />}
          />
          <Route path="culture-library/add-strain" element={<StrainForm />} />
          <Route path="recipes" element={<RecipesHome />} />
          {Object.keys(recipeCategories).map((category) => (
            <Route
              key={category}
              path={`recipes/${category}`}
              element={
                category === "lc-media" ? (
                  <LCMediaPage />
                ) : (
                  <RecipeList
                    category={category as keyof typeof recipeCategories}
                  />
                )
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
          <Route
            path="recipes/lc-media/manage"
            element={<RecipeList category="lc-media" />}
          />
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
          <Route path="history/materials" element={<PreparedPage />} />
          <Route
            path="history/materials/inoculate"
            element={<LegacyInoculation />}
          />
          <Route path="history/materials/:code" element={<PreparedDetail />} />
          <Route path="history/accounting" element={<TransactionsPage />} />
          <Route
            path="inventory/prepared"
            element={<LegacyRedirect to="/history/materials" />}
          />
          <Route
            path="inventory/prepared/inoculate"
            element={<LegacyRedirect to="/history/materials/inoculate" />}
          />
          <Route
            path="inventory/prepared/prepare"
            element={<LegacyRedirect to="/" />}
          />
          <Route
            path="inventory/prepared/:code"
            element={<OldMaterialRedirect />}
          />
          <Route
            path="inventory/recipes"
            element={<LegacyRedirect to="/recipes" />}
          />
          <Route
            path="inventory/transactions"
            element={<LegacyRedirect to="/history/accounting" />}
          />
          <Route
            path="inventory/receive-acquisition"
            element={<LegacyRedirect to="/acquisitions/receive" />}
          />
          <Route
            path="inventory/receive-culture"
            element={<LegacyRedirect to="/acquisitions/receive-culture" />}
          />
          <Route
            path="inventory/receive-spores"
            element={<LegacyRedirect to="/acquisitions/receive-spores" />}
          />
          <Route
            path="inventory/strains/new"
            element={<LegacyRedirect to="/culture-library/add-strain" />}
          />
          <Route
            path="inventory/*"
            element={<LegacyRedirect to="/acquisitions" />}
          />
          <Route path="cultivation/register-grow" element={<GrowForm />} />
          <Route path="culture-library" element={<CultureLibrary />} />
          {Object.entries({
            acquire: "/acquisitions/receive",
            "receive-culture": "/acquisitions/receive-culture",
            "receive-spores": "/acquisitions/receive-spores",
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
          <Route path="reports" element={<Reports />} />
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
