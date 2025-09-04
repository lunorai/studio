import { inject } from "mobx-react";
import React from "react";
import Running from "../../assets/running";

const injector = inject(({ store }) => {
  return {
    SDK: store?.SDK,
  };
});

export const Spinner = injector(({ SDK, visible = true, ...props }) => {
  const size = React.useMemo(() => {
    switch (props.size) {
      case "large":
        return 60;
      case "middle":
        return 60;
      case "small":
        return 60;
      default:
        return 60;
    }
  }, [props.size]);

  const source = Running.default;

  const videoStyles = {
    width: "100%",
    height: "100%",
    objectFit: "contain",
  };

  const ExternalSpinner = SDK?.spinner;

  // Add rotate+scale animation similar to the provided framer-motion example
  React.useEffect(() => {
    const styleId = "ls-lunor-spinner-anim";
    if (!document.getElementById(styleId)) {
      const style = document.createElement("style");
      style.id = styleId;
      style.textContent = `@keyframes ls-lunor-spin {\n  0% { transform: scale(1) rotate(0deg); }\n  50% { transform: scale(1.2) rotate(180deg); }\n  100% { transform: scale(1) rotate(360deg); }\n}`;
      document.head.appendChild(style);
    }
  }, []);

  return visible ? (
    <div
      {...props}
      style={{ width: size, height: size }}
      children={
        <div style={{ width: "100%", height: "100%" }}>
          {ExternalSpinner ? (
            <ExternalSpinner size={size} />
          ) : (
            <img
              src={source.x1}
              srcSet={[`${source.x1} 1x`, `${source.x2} 2x`].join(",")}
              style={{ ...videoStyles, animation: "ls-lunor-spin 2s ease-in-out infinite" }}
              alt="opossum loader"
            />
          )}
        </div>
      }
    />
  ) : null;
});
