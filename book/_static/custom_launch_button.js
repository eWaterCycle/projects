// This code is used to make the launch button on top of the webpage

window.addEventListener("DOMContentLoaded", () => {
  // Create the modal HTML
  const modalHTML = `
    <div id="customModal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background-color:rgba(0,0,0,0.5); z-index:1000;">
      <div style="background:white; padding:20px; max-width:400px; margin:100px auto; border-radius:8px; box-shadow:0 2px 10px rgba(0,0,0,0.3);">
        <h3 style="margin-top:0;">Enter your JupyterHub URL</h3>
        <input type="text" id="jupyterUrlInput" value="https://extendingdcache.ewatercycle-tud.src.surf-hosted.nl/jupyter" style="width:100%; padding:8px; margin-top:10px;"/>
        <div style="margin-top:15px; text-align:right;">
          <button id="launchBtn" style="padding:8px 12px; margin-right:10px;">Launch</button>
          <button id="cancelBtn" style="padding:8px 12px;">Cancel</button>
        </div>
      </div>
    </div>
  `;
  document.body.insertAdjacentHTML("beforeend", modalHTML);

  // Create the custom button
  const header = document.querySelector("header");
  if (header) {
    const customButton = document.createElement("a");
    customButton.textContent = "🚀 Launch eWaterCycle JupyterHub";
    customButton.className = "custom-launch-button";
    customButton.style.backgroundColor = "#007ACC";
    customButton.style.color = "white";
    customButton.style.padding = "6px 12px";
    customButton.style.marginLeft = "10px";
    customButton.style.borderRadius = "4px";
    customButton.style.textDecoration = "none";
    customButton.style.fontWeight = "bold";
    customButton.style.cursor = "pointer";

    customButton.addEventListener("click", () => {
      document.getElementById("customModal").style.display = "block";
    });

    header.appendChild(customButton);
  }

  // Modal button logic
  const launchBtn = document.getElementById("launchBtn");
  const cancelBtn = document.getElementById("cancelBtn");
  const input = document.getElementById("jupyterUrlInput");
  const modal = document.getElementById("customModal");

  launchBtn.addEventListener("click", () => {
    const baseUrl = input.value.trim();

    if (baseUrl.startsWith("https://")) {
      const repo = encodeURIComponent("https://github.com/eWaterCycle/projects");
      const branch = "workshops";
      // const notebookPath = "getting-started/book/content/first_model_run/first_run.ipynb"; // Change to your desired notebook
      const notebookPath = "projects/book/tutorials_examples/6_Africa/1a_HBV_Africa.ipynb"; // Change to your desired notebook

      const nbgitpullerUrl = `${baseUrl}/hub/user-redirect/git-pull?repo=${repo}&branch=${branch}&urlpath=lab/tree/${notebookPath}`;
      window.open(nbgitpullerUrl, "_blank");
      modal.style.display = "none";
      input.value = "";
    } else {
      alert("Please enter a valid HTTPS URL.");
    }
  });

  cancelBtn.addEventListener("click", () => {
    modal.style.display = "none";
    input.value = "";
  });
});