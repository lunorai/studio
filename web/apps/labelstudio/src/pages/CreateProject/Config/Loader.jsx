const Loader = ({ size = 40 }) => {
    return (
      <div
        style={{
          width: size,
          height: size,
          border: `${size / 8}px solid #f3f3f3`,
          borderTop: `${size / 8}px solid #EABE00`,
          borderRadius: "50%",
          animation: "spin 1s linear infinite",
        }}
      />
    );
  };
  
  // Add this keyframes once in your global CSS or styled-component
  const style = document.createElement("style");
  style.innerHTML = `
    @keyframes spin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
  `;
  document.head.appendChild(style);
  
  export default Loader;
  