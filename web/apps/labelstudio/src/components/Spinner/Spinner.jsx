import { cn } from "../../utils/bem";
import "./Spinner.scss";
import Running from "../../../../../libs/datamanager/src/assets/running";
import React from "react";

export const Spinner = ({ className, style, size = 40, stopped = false }) => {
  const rootClass = cn("spinner-ls");

  React.useEffect(() => {
    const styleId = "ls-lunor-spin-anim";
    if (!document.getElementById(styleId)) {
      const styleEl = document.createElement("style");
      styleEl.id = styleId;
      styleEl.textContent = `@keyframes ls-lunor-spin {\n  0% { transform: scale(1) rotate(0deg); }\n  50% { transform: scale(1.2) rotate(180deg); }\n  100% { transform: scale(1) rotate(360deg); }\n}`;
      document.head.appendChild(styleEl);
    }
  }, []);

  const sizeWithUnit = typeof size === "number" ? `${size}px` : size;
  const source = Running.full;
  const imgStyles = { width: "100%", height: "100%", objectFit: "contain", animation: stopped ? undefined : "ls-lunor-spin 2s ease-in-out infinite" };

  return (
    <div className={rootClass.mix(className)} style={{ ...(style ?? {}), "--spinner-size": sizeWithUnit }}>
      <img src={source.x1} srcSet={`${source.x1} 1x, ${source.x2} 2x`} style={imgStyles} alt="loading" />
    </div>
  );
};
