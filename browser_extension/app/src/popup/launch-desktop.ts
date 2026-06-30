export function launchDesktop(): void {
  const frame = document.createElement("iframe");
  frame.style.display = "none";
  frame.src = "ghostdownloader://launch";
  document.body.appendChild(frame);
  setTimeout(() => frame.remove(), 2000);
}
