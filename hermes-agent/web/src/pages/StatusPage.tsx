import { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Clock,
  Cpu,
  Database,
  Radio,
  Wifi,
  WifiOff,
} from "lucide-react";
import { api } from "@/lib/api";
import type { GatewayStatus, PlatformStatus, SessionInfo, StatusResponse } from "@/lib/api";
import { timeAgo, isoTimeAgo } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const PLATFORM_STATE_BADGE: Record<string, { variant: "success" | "warning" | "destructive"; label: string }> = {
  connected: { variant: "success", label: "Connected" },
  disconnected: { variant: "warning", label: "Disconnected" },
  fatal: { variant: "destructive", label: "Error" },
};

const GATEWAY_STATE_DISPLAY: Record<string, { badge: "success" | "warning" | "destructive" | "outline"; label: string }> = {
  running: { badge: "success", label: "Running" },
  starting: { badge: "warning", label: "Starting" },
  startup_failed: { badge: "destructive", label: "Failed" },
  stopped: { badge: "outline", label: "Stopped" },
};

function gatewayValue(status: StatusResponse): string {
  if (status.gateway_running) return `PID ${status.gateway_pid}`;
  if (status.gateway_state === "startup_failed") return "Start failed";
  return "Not running";
}

function gatewayBadge(status: StatusResponse) {
  const info = status.gateway_state ? GATEWAY_STATE_DISPLAY[status.gateway_state] : null;
  if (info) return info;
  return status.gateway_running
    ? { badge: "success" as const, label: "Running" }
    : { badge: "outline" as const, label: "Off" };
}

function gatewayStatusBadge(gateway: GatewayStatus) {
  const info = gateway.gateway_state ? GATEWAY_STATE_DISPLAY[gateway.gateway_state] : null;
  if (info) return info;
  return gateway.gateway_running
    ? { badge: "success" as const, label: "Running" }
    : { badge: "outline" as const, label: "Off" };
}

export default function StatusPage() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [sessions, setSessions] = useState<SessionInfo[]>([]);

  useEffect(() => {
    const load = () => {
      api.getStatus().then(setStatus).catch(() => {});
      api.getSessions().then(setSessions).catch(() => {});
    };
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, []);

  if (!status) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  const gwBadge = gatewayBadge(status);

  const items = [
    {
      icon: Cpu,
      label: "Agent",
      value: `v${status.version}`,
      badgeText: "Live",
      badgeVariant: "success" as const,
    },
    {
      icon: Radio,
      label: "Gateway",
      value: gatewayValue(status),
      badgeText: gwBadge.label,
      badgeVariant: gwBadge.badge,
    },
    {
      icon: Activity,
      label: "Active Sessions",
      value: status.active_sessions > 0 ? `${status.active_sessions} running` : "None",
      badgeText: status.active_sessions > 0 ? "Live" : "Off",
      badgeVariant: (status.active_sessions > 0 ? "success" : "outline") as "success" | "outline",
    },
  ];

  const gateways = status.gateways?.length ? status.gateways : [{
    gateway_exit_reason: status.gateway_exit_reason,
    gateway_pid: status.gateway_pid,
    gateway_platforms: status.gateway_platforms,
    gateway_running: status.gateway_running,
    gateway_state: status.gateway_state,
    gateway_updated_at: status.gateway_updated_at,
    is_default: status.active_profile === "default",
    model: null,
    name: status.active_profile ?? "default",
    path: status.hermes_home,
    provider: null,
  }];
  const platforms = Object.entries(status.gateway_platforms ?? {});
  const activeSessions = sessions.filter((s) => s.is_active);
  const recentSessions = sessions.filter((s) => !s.is_active).slice(0, 5);

  // Collect alerts that need attention
  const alerts: { message: string; detail?: string }[] = [];
  const unhealthyGateways = gateways.filter((gateway) => (
    gateway.gateway_state === "startup_failed" || !gateway.gateway_running
  ));
  for (const gateway of unhealthyGateways) {
    alerts.push({
      message: `${gateway.name} gateway ${gateway.gateway_state === "startup_failed" ? "failed to start" : "is not running"}`,
      detail: gateway.gateway_exit_reason ?? undefined,
    });
  }
  for (const gateway of gateways) {
    const gatewayPlatforms = Object.entries(gateway.gateway_platforms ?? {});
    const failedPlatforms = gatewayPlatforms.filter(([, info]) => info.state === "fatal" || info.state === "disconnected");
    for (const [name, info] of failedPlatforms) {
      alerts.push({
        message: `${gateway.name} ${name} ${info.state === "fatal" ? "error" : "disconnected"}`,
        detail: info.error_message ?? undefined,
      });
    }
  }


  return (
    <div className="flex flex-col gap-6">
      {/* Alert banner — breaks grid monotony for critical states */}
      {alerts.length > 0 && (
        <div className="border border-destructive/30 bg-destructive/[0.06] p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
            <div className="flex flex-col gap-2 min-w-0">
              {alerts.map((alert, i) => (
                <div key={i}>
                  <p className="text-sm font-medium text-destructive">{alert.message}</p>
                  {alert.detail && (
                    <p className="text-xs text-destructive/70 mt-0.5">{alert.detail}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        {items.map(({ icon: Icon, label, value, badgeText, badgeVariant }) => (
          <Card key={label}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">{label}</CardTitle>
              <Icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>

            <CardContent>
              <div className="text-2xl font-bold font-display">{value}</div>

              {badgeText && (
                <Badge variant={badgeVariant} className="mt-2">
                  {badgeVariant === "success" && (
                    <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
                  )}
                  {badgeText}
                </Badge>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {platforms.length > 0 && (
        <PlatformsCard platforms={platforms} />
      )}

      {gateways.length > 0 && (
        <GatewaysCard activeProfile={status.active_profile} gateways={gateways} />
      )}

      {activeSessions.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-success" />
              <CardTitle className="text-base">Active Sessions</CardTitle>
            </div>
          </CardHeader>

          <CardContent className="grid gap-3">
            {activeSessions.map((s) => (
              <div
                key={s.id}
                className="flex items-center justify-between border border-border p-3"
              >
                <div className="flex flex-col gap-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm">{s.title ?? "Untitled"}</span>

                    <Badge variant="success" className="text-[10px]">
                      <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
                      Live
                    </Badge>
                  </div>

                  <span className="text-xs text-muted-foreground">
                    <span className="font-mono-ui">{s.model ?? "unknown"}</span> · {s.message_count} msgs · {timeAgo(s.last_active)}
                  </span>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {recentSessions.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Clock className="h-5 w-5 text-muted-foreground" />
              <CardTitle className="text-base">Recent Sessions</CardTitle>
            </div>
          </CardHeader>

          <CardContent className="grid gap-3">
            {recentSessions.map((s) => (
              <div
                key={s.id}
                className="flex items-center justify-between border border-border p-3"
              >
                <div className="flex flex-col gap-1">
                  <span className="font-medium text-sm">{s.title ?? "Untitled"}</span>

                  <span className="text-xs text-muted-foreground">
                    <span className="font-mono-ui">{s.model ?? "unknown"}</span> · {s.message_count} msgs · {timeAgo(s.last_active)}
                  </span>

                  {s.preview && (
                    <span className="text-xs text-muted-foreground/70 truncate max-w-md">
                      {s.preview}
                    </span>
                  )}
                </div>

                <Badge variant="outline" className="text-[10px]">
                  <Database className="mr-1 h-3 w-3" />
                  {s.source ?? "local"}
                </Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function GatewaysCard({ activeProfile, gateways }: GatewaysCardProps) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Radio className="h-5 w-5 text-muted-foreground" />
          <CardTitle className="text-base">Agent Gateways</CardTitle>
        </div>
      </CardHeader>

      <CardContent className="grid gap-3">
        {gateways.map((gateway) => {
          const display = gatewayStatusBadge(gateway);
          const gatewayPlatforms = Object.entries(gateway.gateway_platforms ?? {});
          const IconComponent = gateway.gateway_running ? Wifi : AlertTriangle;

          return (
            <div
              key={gateway.name}
              className="flex items-center justify-between gap-4 border border-border p-3"
            >
              <div className="flex min-w-0 items-center gap-3">
                <IconComponent className={`h-4 w-4 shrink-0 ${
                  gateway.gateway_running ? "text-success" : "text-warning"
                }`} />

                <div className="flex min-w-0 flex-col gap-0.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium">{gateway.name}</span>

                    {gateway.name === activeProfile && (
                      <Badge variant="outline" className="text-[10px]">Active</Badge>
                    )}

                    {gateway.gateway_pid && (
                      <span className="text-xs text-muted-foreground">PID {gateway.gateway_pid}</span>
                    )}
                  </div>

                  <span className="truncate text-xs text-muted-foreground">
                    {gatewayPlatforms.length > 0
                      ? gatewayPlatforms.map(([name, info]) => `${name}: ${info.state}`).join(" · ")
                      : "No connected platforms"}
                  </span>

                  {gateway.gateway_updated_at && (
                    <span className="text-xs text-muted-foreground">
                      Last update: {isoTimeAgo(gateway.gateway_updated_at)}
                    </span>
                  )}

                  {gateway.gateway_exit_reason && (
                    <span className="text-xs text-destructive">{gateway.gateway_exit_reason}</span>
                  )}
                </div>
              </div>

              <Badge variant={display.badge}>
                {display.badge === "success" && (
                  <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
                )}
                {display.label}
              </Badge>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

function PlatformsCard({ platforms }: PlatformsCardProps) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Radio className="h-5 w-5 text-muted-foreground" />
          <CardTitle className="text-base">Connected Platforms</CardTitle>
        </div>
      </CardHeader>

      <CardContent className="grid gap-3">
        {platforms.map(([name, info]) => {
          const display = PLATFORM_STATE_BADGE[info.state] ?? {
            variant: "outline" as const,
            label: info.state,
          };
          const IconComponent = info.state === "connected" ? Wifi : info.state === "fatal" ? AlertTriangle : WifiOff;

          return (
            <div
              key={name}
              className="flex items-center justify-between border border-border p-3"
            >
              <div className="flex items-center gap-3">
                <IconComponent className={`h-4 w-4 ${
                  info.state === "connected"
                    ? "text-success"
                    : info.state === "fatal"
                      ? "text-destructive"
                      : "text-warning"
                }`} />

                <div className="flex flex-col gap-0.5">
                  <span className="text-sm font-medium capitalize">{name}</span>

                  {info.error_message && (
                    <span className="text-xs text-destructive">{info.error_message}</span>
                  )}

                  {info.updated_at && (
                    <span className="text-xs text-muted-foreground">
                      Last update: {isoTimeAgo(info.updated_at)}
                    </span>
                  )}
                </div>
              </div>

              <Badge variant={display.variant}>
                {display.variant === "success" && (
                  <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
                )}
                {display.label}
              </Badge>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

interface PlatformsCardProps {
  platforms: [string, PlatformStatus][];
}

interface GatewaysCardProps {
  activeProfile: string;
  gateways: GatewayStatus[];
}
