const EU_MINER_HOSTS = new Set([
  "eu.quantforge.giorgiy.org",
  "miner.quantforge.giorgiy.org",
]);

export function shouldShowEuMiner(pathname: string, hostname: string): boolean {
  const path = pathname.replace(/\/+$/, "") || "/";
  return path === "/eu-miner" || EU_MINER_HOSTS.has(hostname.toLowerCase());
}
