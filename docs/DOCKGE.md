# Deploying Cultivatinator through Dockge

These examples target Debian 13, Docker Engine/Compose v2 and an existing Dockge installation. They move management of the application to Dockge while keeping its source and persistent data in place. They do not change the application's database schema or backup format.

| Location | Purpose |
| --- | --- |
| `/opt/stacks/cultivatinator/compose.yaml` | Dockge stack definition copied from `examples/dockge/compose.yaml` |
| `/opt/stacks/cultivatinator/.env` | Local stack settings copied/customized from `examples/dockge/.env.example` |
| `/storage/tv/cultivatinator` | Existing Git checkout, Dockerfile and persistent data; remains in place |
| `/storage/tv/cultivatinator/database/` | Existing SQLite database, including WAL sidecars when present |
| `/storage/tv/cultivatinator/photos/`, `files/`, `settings/`, `backups/` | Existing photographs, persistent files/settings and retained backups |
| `/run/cultivatinator-maintenance` | Existing root-owned helper socket/key directory; read-only in the app |

The application remains one container on port **8085**, running as **10001:10001**, with `no-new-privileges` and all capabilities dropped. It retains the `cultivatinator` Compose project, `app` service and `cultivatinator:local` image. There is no `container_name`, new database service, named data volume or Docker-socket mount in the app. The existing host systemd helper retains its restricted Unix channel and privileged stop/restore/restart role.

## 1. Make the source available to Dockge

The application stack directory and build context are different. The sample uses the absolute build context **`/storage/tv/cultivatinator`**, not `.` and not a path relative to `/opt/stacks`. The Dockerfile is taken from that checkout.

Docker Compose sends build context from its **client filesystem**. If Dockge runs in a container, `/opt/stacks` and the Docker socket alone are insufficient: the source path must also be visible inside the Dockge container at the same absolute location.

Edit the deployment used to run **Dockge itself** and add this read-only source bind under its existing service's `volumes`. Keep its current stack-directory, Docker-socket and Dockge-data mounts:

```yaml
services:
  dockge:
    volumes:
      # Additional bind; retain the existing Dockge mounts.
      - /storage/tv/cultivatinator:/storage/tv/cultivatinator:ro
```

Apply that change using the normal management procedure for your Dockge installation. Its Compose file location depends on how Dockge was installed; this is not a replacement Dockge configuration. Keep Dockge's stack directory set/mounted as `/opt/stacks`.

This read-only source bind is for building. The application's separate `/data` bind remains writable on the Debian host. The checkout's existing `.dockerignore` excludes `.git`, live `.env`, database/photos/files/settings/backups, dependencies and runtime files from the build context. Neither Dockge nor the app needs a new maintenance-helper secret copied into its stack settings; the app uses the existing read-only runtime-directory bind. Dockge already controls Docker and should retain its existing administrative access restrictions.

## 2. Prepare the stack without starting a second app

Use the existing source checkout at `/storage/tv/cultivatinator`. Do not clone over it, copy its database into `/opt/stacks`, or replace its data directory. Keep a verified backup outside this server before planned maintenance.

In Dockge choose **Compose / Create Stack** and name the stack **`cultivatinator`**. Paste `examples/dockge/compose.yaml` into its Compose editor and save it **without Deploy/Start** yet. Add the environment settings in Dockge's `.env` editor. Alternatively, prepare the files on the Debian host, then use Dockge's **Scan Stacks Folder** / refresh action to discover the saved stack:

```bash
sudo install -d -m 0755 /opt/stacks/cultivatinator
sudo cp -n /storage/tv/cultivatinator/examples/dockge/compose.yaml /opt/stacks/cultivatinator/compose.yaml
sudo cp -n /storage/tv/cultivatinator/examples/dockge/.env.example /opt/stacks/cultivatinator/.env
```

The no-clobber copy commands leave existing stack files intact. If files already exist, review/update them in Dockge instead of assuming the copy changed them. A live `.env` is local configuration and must never be committed.

The sample's five settings are:

```dotenv
APP_PORT=8085
DATA_DIR=/storage/tv/cultivatinator
MAINTENANCE_DIR=/run/cultivatinator-maintenance
CULTIVATINATOR_BACKUP_AUTH_MODE=trusted_lan
CULTIVATINATOR_TRUSTED_NETWORKS=192.168.68.0/24
```

Adjust the host port or absolute paths only when they match the existing installation. `DATA_DIR` is independent of the source build context. If the checkout moves, change `build.context` and Dockge's source bind together. `MAINTENANCE_DIR` must be the helper's actual runtime directory: the supplied installer uses `/run/cultivatinator-maintenance`; changing an environment value alone does not move that service.

**Trusted LAN Mode grants backup and restore administration to every client in the allowed CIDRs without a password.** Use the direct LAN IP or a private hostname. Forwarded requests and public DNS hostnames are rejected; loopback and Docker gateway addresses are not implicitly trusted. Deletion and data replacement retain explicit confirmation and CSRF protection.

For password-protected administration, replace the two authentication values with:

```dotenv
CULTIVATINATOR_BACKUP_AUTH_MODE=password
CULTIVATINATOR_TRUSTED_NETWORKS=
```

Existing password credentials remain in root-private helper state. New password-mode installations establish the passphrase through Settings with the installer's one-time setup code. Do not put passwords, tokens or channel keys in `.env`. The example Compose file also defaults to password mode if the environment setting is omitted; the root repository examples keep their existing secure defaults.

## 3. Validate paths, naming and existing data

Validate the saved stack from the Debian host; this command does not start containers:

```bash
sudo docker compose --project-directory /opt/stacks/cultivatinator --env-file /opt/stacks/cultivatinator/.env -f /opt/stacks/cultivatinator/compose.yaml config --quiet
```

The helper installer resolves the same stack directory's `.env`. Avoid conflicting exported `APP_PORT`, `DATA_DIR`, `MAINTENANCE_DIR`, `CULTIVATINATOR_*` or `COMPOSE_PROJECT_NAME` values in the host shell or Dockge container. The effective project must remain `cultivatinator`; a CLI/Dockge project override can override the file's `name`.

Check the currently managed app and its old Compose path before switching management:

```bash
sudo docker compose -f /storage/tv/cultivatinator/compose.yaml ps -a
sudo docker ps -a --filter label=com.docker.compose.project=cultivatinator --filter label=com.docker.compose.service=app --format '{{.Names}} {{.Status}}'
sudo test -f /storage/tv/cultivatinator/database/cultivatinator.sqlite3
```

For an existing installation, the database check must succeed. Confirm the existing app uses this same project/service, `/data` host bind and UID/GID 10001; note any intentional custom port or data path and carry it into the Dockge `.env`. If project/service identity differs, stop here and adapt the saved stack to the existing identity before starting it. Renaming only the stack can create another project instead of adopting the original one. The application lease is a final safeguard, not a substitute for one deployment owner.

Both host directories in the example use `create_host_path: false`: a mistyped data/helper path fails instead of silently creating a new empty directory. The app can initialize a fresh database inside an existing but incorrect data root, so verify the actual SQLite file before starting an existing installation. Do not fix an unexpected empty library by resetting or deleting the database.

## 4. Switch an existing installation to Dockge management

This is a planned application restart, not a cultivation-data restore. Finish any active backup/restore and keep the old Compose file and its `.env` intact for reference. Stop any other automation that starts the app from the old Compose path; the maintenance helper remains part of the installation.

Stop the existing application through its current source-checkout Compose file:

```bash
sudo docker compose --project-directory /storage/tv/cultivatinator -f /storage/tv/cultivatinator/compose.yaml stop app
```

Do not start the old definition again after Dockge takes ownership. No `down -v`, volume pruning, data copying, credential reset or recursive `chown` is part of this migration. The old stopped container belongs to the same project/service and can be reused or recreated by the new definition; there must be only one app instance.

Refresh the helper from the existing checkout, **pointing at the Dockge Compose file**:

```bash
sudo python3 /storage/tv/cultivatinator/scripts/install_backup_helper.py install --data-root /storage/tv/cultivatinator --compose-file /opt/stacks/cultivatinator/compose.yaml
sudo systemctl status cultivatinator-maintenance.service --no-pager
```

The installer loads the Dockge stack's resolved configuration, validates the `/data` bind and authentication policy, and refreshes its root-owned code/configuration. It retains stored backup archives, schedules, password credentials and recovery state. It refuses an unresolved restore. The helper uses a root-private resolved Compose snapshot to manage the existing `app`; it must not keep targeting an outdated source-checkout configuration. If `DATA_DIR` was customized, use that exact absolute value for `--data-root` as well.

In Dockge, open the saved stack and choose **Build / Build & Start / Deploy**, using the action that builds the local Dockerfile and recreates/starts the application. Button labels vary by Dockge version. A registry **Pull** alone does not update a locally built source image. Keep the same project/service and data bind during recreation.

For a host-side equivalent (use one management path, not a second stack):

```bash
sudo docker compose --project-directory /opt/stacks/cultivatinator -f /opt/stacks/cultivatinator/compose.yaml up -d --build --wait
```

Because the new definition uses the existing `cultivatinator` / `app` identity, Compose manages the existing service rather than launching another project. The bind-mounted SQLite database, photographs, `backups/` and schedule remain at their original paths. No application directories are moved. The helper's root-private credentials and history also stay in place.

## 5. Check startup and backup administration

Check Dockge status/logs, then:

```bash
sudo docker compose --project-directory /opt/stacks/cultivatinator -f /opt/stacks/cultivatinator/compose.yaml ps
curl --fail http://127.0.0.1:8085/api/health
```

Health must report database `ok` and migrations `current`. Open `http://SERVER-LAN-IP:8085` from `192.168.68.0/24` (or the configured port/network). Check existing Culture Library records, fruiting journals, harvests and photo originals/thumbnails. In Settings, Trusted LAN Mode should open Backup & Restore immediately; password mode should use the existing passphrase. Confirm retained server backups, last/next automatic runs and retention settings. Create/Verify/Download a backup and retain an external copy. Confirm a Restore preview can be verified then cancelled; test destructive restores only in a disposable installation.

There should be exactly one application service. A healthy HTTP response alone is insufficient if it is served by the old stack/container: check Dockge's project/service and expected data bind too. The health endpoint does not require backup authentication, so it can be queried on host loopback even when that address is not a trusted backup client.

## 6. Update through Dockge

Dockge manages the stack; Git still manages source. Update the **existing** `/storage/tv/cultivatinator` checkout on the approved branch, rather than cloning a second source copy under `/opt/stacks`:

```bash
git -C /storage/tv/cultivatinator pull --ff-only
```

Review release/migration instructions and keep a verified external backup before rebuilding. Do not blindly recopy the example `.env` over customized settings. Review relevant Compose example changes in Dockge, validate the saved configuration, and refresh the helper using the same Dockge `--compose-file` command from step 4 when helper code, schema compatibility, auth mode or stack settings change. Then use Dockge's build/recreate/deploy action and repeat the health/data checks. No unattended update, production deployment or database downgrade is implied by these instructions.

If returning management to the old Compose file, first stop the Dockge-managed service, ensure the old definition's environment points to the same data/authentication settings, refresh the helper with that old Compose path, then start that same project/service. Do not run both definitions independently. Switching management is not a reason to extract a backup or move the database.

## Troubleshooting

| Symptom | Check/action |
| --- | --- |
| Build context `/storage/tv/cultivatinator` not found | Confirm the Git checkout/Dockerfile exists on the Debian host **and** the same absolute read-only source bind exists inside Dockge. Recreate Dockge after changing its own mount list. |
| Build uses `/opt/stacks/cultivatinator` and cannot find source | Use the provided absolute `build.context`, not `.`. Do not copy database files or another checkout into the stack to bypass this error. |
| Invalid/missing bind source | Verify `DATA_DIR` and `MAINTENANCE_DIR` on the Debian host. `create_host_path: false` intentionally rejects a missing path. |
| Permission denied | Inspect app logs and the existing data-directory ownership for UID/GID 10001. Do not recursively change ownership of the co-located Git checkout or use world-writable permissions. The helper runtime directory/key/socket have root:10001 ownership with restricted modes; run the installer rather than weakening them. |
| Port 8085 is allocated | Check for an old app/project still running. Stop it before migration. If another application intentionally uses that port, set `APP_PORT` and refresh the helper's resolved configuration. |
| Two app containers / helper expects one | Check Compose project/service labels and Dockge's stack name/project override. Keep `cultivatinator` / `app`; do not enable scaling or run another stack against `/data`. |
| Backup helper unavailable | Check systemd logs, the read-only runtime bind and the helper installation. It is a host service, not a second service to add to the application stack. |
| Auth configuration differs from helper | Validate `/opt/stacks/cultivatinator/.env`, re-run the installer with **that stack's Compose path**, and recreate the app so both use the same resolved policy. |
| Trusted LAN HTTP 403 | Connect directly from the configured subnet using a LAN IP/private hostname. Forwarding headers, public DNS hosts and unlisted networks are rejected; do not trust Docker gateways/proxies just to bypass the check. |
| Unexpected empty library or missing photos | Stop the app and inspect the original host bind/database and logs. Do not initialize/reset data or copy a different database over it. |
| Migration/startup failure | Preserve data/logs and follow the release or emergency-recovery instructions. Never delete the SQLite file to make startup succeed. |

Useful host diagnostics, with no credential output:

```bash
sudo docker compose --project-directory /opt/stacks/cultivatinator -f /opt/stacks/cultivatinator/compose.yaml logs --tail=100 app
sudo journalctl -u cultivatinator-maintenance.service -n 100 --no-pager
```

See [backup formats, modes and emergency recovery](MILESTONE_2D2.md) for restore-specific recovery. The existing root `compose.yaml` and `.env.example` remain usable for checkout-based management; the new files are opt-in Dockge examples.

## Validation performed

Docker Compose **2.40.3** successfully resolved the example copied into a separate temporary stack directory, including the supplied Trusted LAN profile, password alternative, password defaults without `.env`, and overrides for all five variables. Checks confirmed the fixed source build context, `cultivatinator` / `app` identity, image/user, port mapping, bind paths, read-only helper mount, missing-path protections and container security options. The unchanged root Compose/environment examples also passed `config --quiet`.

The actual helper installer was run with the copied stack's Compose path and `.env` in both modes in a disposable, network-disabled container. Its resolved policy, root-owned code and frozen Compose snapshot matched the examples, and a temporary SQLite database's bytes remained unchanged. Systemctl was stubbed; no application, live helper or host Docker socket was used by that validation container. This validates installer/configuration compatibility, not a live Debian/systemd or Dockge UI deployment.

The latest-main baseline also passed **289 backend tests**, **173 frontend tests** and the production frontend build. One existing Starlette/AnyIO deprecation warning remains. No application code, root deployment configuration, schema or existing data is changed by this examples/documentation branch. Debian/Dockge acceptance is a separate operator action.
