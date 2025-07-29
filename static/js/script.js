document.addEventListener('DOMContentLoaded', () => {
  const dropArea = document.getElementById("drop-area");
  const fileInput = document.getElementById("fileInput");
  const uploadBtn = document.getElementById("uploadBtn");
  const summarizeBtn = document.getElementById("summarizeBtn");
  const resultBox = document.getElementById("result");
  const summaryText = document.getElementById("summaryText");
  const speakBtn = document.getElementById("speakButton");
  const audioPlayer = document.getElementById("audioPlayer");
  const langSelect = document.getElementById("languageSelect");
  const loader = document.getElementById("loader");
  const fileInfo = document.getElementById("fileInfo");

  // Drag and drop functionality
  dropArea.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropArea.classList.add("highlight");
  });
  dropArea.addEventListener("dragleave", () => {
    dropArea.classList.remove("highlight");
  });
  dropArea.addEventListener("drop", (e) => {
    e.preventDefault();
    dropArea.classList.remove("highlight");
    fileInput.files = e.dataTransfer.files;
    if (fileInput.files[0]) {
      fileInfo.textContent = `Uploaded File: ${fileInput.files[0].name}`;
      fileInfo.style.display = "block";
    }
  });

  uploadBtn.onclick = () => fileInput.click();

  fileInput.addEventListener("change", () => {
    if (fileInput.files[0]) {
      fileInfo.textContent = `Uploaded File: ${fileInput.files[0].name}`;
      fileInfo.style.display = "block";
    }
  });

  dropArea.addEventListener("click", () => fileInput.click());

  summarizeBtn.addEventListener("click", async () => {
    const file = fileInput.files[0];

    if (!file) {
      alert("Please upload a file (PDF, DOC, DOCX).");
      return;
    }

    loader.style.display = "block";
    resultBox.style.display = "none";
    langSelect.style.display = "none";

    const formData = new FormData();
    formData.append("file", file);

    await new Promise(resolve => setTimeout(resolve, 3000)); // 3-second delay

    try {
      const res = await fetch("/summarize", {
        method: "POST",
        body: formData
      });
      const data = await res.json();

      if (data.error) {
        alert(data.error);
        loader.style.display = "none";
        return;
      }

      loader.style.display = "none";
      summaryText.innerHTML = data.summary;
      resultBox.style.display = "block";
      langSelect.style.display = "inline";
    } catch (error) {
      alert("An error occurred while summarizing.");
      loader.style.display = "none";
    }
  });

  speakBtn.addEventListener("click", async () => {
    const text = summaryText.innerText.trim();
    const lang = langSelect.value || "en";

    if (!text) {
      alert("No summary text to speak.");
      return;
    }

    try {
      const res = await fetch("/speak", {
        method: "POST",
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, lang })
      });
      const data = await res.json();

      if (data.error) {
        alert(data.error);
        return;
      }

      audioPlayer.src = data.audio_path;
      audioPlayer.style.display = "block";

      // Simulate live listening with text highlight animation
      let index = 0;
      const sentences = text.split('. ');
      audioPlayer.play().then(() => {
        function highlightNext() {
          if (index < sentences.length) {
            const sentence = sentences[index].trim() + '.';
            const p = summaryText.querySelector('p');
            if (p) {
              p.innerHTML = p.innerHTML.replace(new RegExp(`(${sentence.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'g'), `<span class="highlight-text">$1</span>`);
              index++;
              setTimeout(highlightNext, 3000); // Adjust timing based on audio length
            }
          }
        }
        highlightNext();
      }).catch(err => {
        alert("Failed to play audio: " + err.message);
      });
    } catch (error) {
      alert("An error occurred while generating audio: " + error.message);
    }
  });

  langSelect.addEventListener("change", async () => {
    const lang = langSelect.value;
    try {
      const res = await fetch("/translate", {
        method: "POST",
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: summaryText.innerText, lang })
      });
      const data = await res.json();
      if (data.error) {
        alert(data.error);
        return;
      }
      summaryText.innerHTML = `<strong>Summary (${lang}):</strong><br>${data.translated}`;
    } catch (error) {
      alert("An error occurred while translating.");
    }
  });

  function toggleLanguage() {
    langSelect.style.display = langSelect.style.display === "none" ? "inline" : "none";
  }

  // Password match validation for registration
  const passwordInput = document.getElementById('password');
  const confirmInput = document.getElementById('confirm_password');
  const registerBtn = document.getElementById('registerBtn');
  if (passwordInput && confirmInput && registerBtn) {
    const validatePasswords = () => {
      if (passwordInput.value === confirmInput.value) {
        registerBtn.disabled = false;
      } else {
        registerBtn.disabled = true;
        alert("Passwords do not match");
      }
    };
    passwordInput.addEventListener('input', validatePasswords);
    confirmInput.addEventListener('input', validatePasswords);
  }

  // Registration form submission
  const registerForm = document.getElementById('register-form');
  if (registerForm) {
    registerForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const formData = {
        name: document.getElementById('name').value,
        email: document.getElementById('email').value,
        username: document.getElementById('username').value,
        password: document.getElementById('password').value
      };
      try {
        const response = await fetch('/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(formData)
        });
        const data = await response.json();
        if (data.status === 'success') {
          alert(data.message);
          window.location.href = '/login';
        } else {
          alert(data.message);
        }
      } catch (error) {
        alert('Something went wrong!');
      }
    });
  }

  // Profile form handling
  const profileForm = document.getElementById('profileForm');
  if (profileForm) {
    fetch('/profile')
      .then(res => res.json())
      .then(data => {
        document.getElementById('name').value = data.name;
        document.getElementById('email').value = data.email;
        document.getElementById('phone').value = data.phone || '';
      });

    profileForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const formData = {
        name: document.getElementById('name').value,
        email: document.getElementById('email').value,
        phone: document.getElementById('phone').value
      };
      try {
        const res = await fetch('/profile', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(formData)
        });
        const data = await res.json();
        alert('Profile updated successfully!');
      } catch (error) {
        alert('An error occurred while updating profile.');
      }
    });
  }
});