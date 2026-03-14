export function formatBytes(value?: number): string {
  if (value === undefined || Number.isNaN(value)) {
    return "n/a";
  }

  if (value < 1024) {
    return `${value} B`;
  }

  const units = ["KB", "MB", "GB", "TB"];
  let size = value;
  let unitIndex = -1;

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }

  return `${size.toFixed(size >= 10 ? 0 : 1)} ${units[unitIndex]}`;
}

export function formatRelativeTime(value?: string): string {
  if (!value) {
    return "n/a";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  const diffMs = date.getTime() - Date.now();
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  const divisions: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ["day", 1000 * 60 * 60 * 24],
    ["hour", 1000 * 60 * 60],
    ["minute", 1000 * 60],
    ["second", 1000],
  ];

  for (const [unit, amount] of divisions) {
    const delta = diffMs / amount;
    if (Math.abs(delta) >= 1 || unit === "second") {
      return formatter.format(Math.round(delta), unit);
    }
  }

  return "just now";
}

export function formatTimestamp(value?: string): string {
  if (!value) {
    return "n/a";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

export function formatDuration(seconds?: number): string {
  if (seconds === undefined || Number.isNaN(seconds)) {
    return "n/a";
  }

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainingSeconds = Math.floor(seconds % 60);

  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }

  if (minutes > 0) {
    return `${minutes}m ${remainingSeconds}s`;
  }

  return `${remainingSeconds}s`;
}

export function clampProgress(value?: number): number {
  if (value === undefined || Number.isNaN(value)) {
    return 0;
  }

  return Math.max(0, Math.min(100, value));
}

export function formatCompactNumber(value?: number): string {
  if (value === undefined || Number.isNaN(value)) {
    return "n/a";
  }

  return new Intl.NumberFormat("en", { notation: "compact" }).format(value);
}
