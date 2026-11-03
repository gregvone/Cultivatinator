import CollapsiblePanel from "../components/CollapsiblePanel";
import FruitingEnvironmentSettings from "../components/FruitingEnvironment";
import { Archive } from "lucide-react";
import type { AppInfo } from "../api";
import { useApi } from "../useApi";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
} from "../components/UI";
export default function Settings() {
  const { data, error, retry } = useApi<AppInfo>("app/info");
  return (
    <>
      <PageHeader
        title="Settings"
        description="Application information and workspace details."
      />
      {error ? (
        <ErrorState error={error} retry={retry} />
      ) : !data ? (
        <LoadingState />
      ) : (
        <CollapsiblePanel
          title="Application Information"
          summary="Version, storage and access"
        >
          <dl className="info-list">
            {Object.entries({
              Application: data.name,
              Version: data.version,
              Environment: data.environment,
              Storage: data.storage,
              Access: "Single user · Private network only",
            }).map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
          <p className="license-note">
            Licensed under GPL-3.0. This software comes with no warranty. See
            the repository LICENSE for terms.
          </p>
        </CollapsiblePanel>
      )}
      <FruitingEnvironmentSettings />
      <div className="settings-backup">
        <CollapsiblePanel title="Backup & Restore">
          <EmptyState
            icon={Archive}
            title="Complete workspace backups are planned."
            description="Downloadable backup and restore will be added in a future milestone. For now, use the stopped-container backup procedure in the deployment documentation."
          />
        </CollapsiblePanel>
      </div>
    </>
  );
}
