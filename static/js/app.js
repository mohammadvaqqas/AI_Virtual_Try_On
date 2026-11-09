const dropZones = {
    person: document.getElementById('dz-person'),
    upper: document.getElementById('dz-upper'),
    lower: document.getElementById('dz-lower')
};
const inputs = {
    person: document.getElementById('person-image'),
    upper: document.getElementById('upper-image'),
    lower: document.getElementById('lower-image')
};
const files = {
    person: null,
    upper: null,
    lower: null
};

const generateBtn = document.getElementById('generate-btn');
const loadingOverlay = document.getElementById('loading-overlay');
const uploadSection = document.getElementById('upload-section');
const resultSection = document.getElementById('result-section');
const resultImg = document.getElementById('result-img');
const originalImg = document.getElementById('original-img');
const sliderHandle = document.querySelector('.slider-handle');
const originalClip = document.querySelector('.original-clip');
const resetBtn = document.getElementById('reset-btn');
const downloadBtn = document.getElementById('download-btn');

Object.keys(dropZones).forEach(key => {
    const zone = dropZones[key];
    const input = inputs[key];

    zone.addEventListener('click', () => input.click());

    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('dragover');
    });

    zone.addEventListener('dragleave', () => {
        zone.classList.remove('dragover');
    });

    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            handleFile(key, e.dataTransfer.files[0]);
        }
    });

    input.addEventListener('change', (e) => {
        if (e.target.files.length) {
            handleFile(key, e.target.files[0]);
        }
    });
});

function handleFile(key, file) {
    if (!file.type.startsWith('image/')) return alert('Please upload an image file.');
    
    files[key] = file;
    const reader = new FileReader();
    reader.onload = (e) => {
        const zone = dropZones[key];
        // Remove old preview if exists
        const oldPreview = zone.querySelector('.preview-image');
        if (oldPreview) oldPreview.remove();

        const img = document.createElement('img');
        img.src = e.target.result;
        img.className = 'preview-image';
        zone.appendChild(img);
        
        // Hide content text
        zone.querySelector('.dz-content').style.opacity = '0';
        
        checkReady();
    };
    reader.readAsDataURL(file);
}

function checkReady() {
    // Allow generation with person + at least one garment (upper OR lower)
    if (files.person && (files.upper || files.lower)) {
        generateBtn.disabled = false;
    } else {
        generateBtn.disabled = true;
    }
}

generateBtn.addEventListener('click', async () => {
    loadingOverlay.classList.remove('hidden');
    generateBtn.disabled = true;

    const formData = new FormData();
    formData.append('person_image', files.person);
    if (files.upper) formData.append('upper_image', files.upper);
    if (files.lower) formData.append('lower_image', files.lower);

    try {
        const res = await fetch('/api/try-on', {
            method: 'POST',
            body: formData
        });
        
        const data = await res.json();
        
        if (!res.ok) throw new Error(data.error || 'Something went wrong');
        
        // Setup Result
        if (data.resultBase64) {
             resultImg.src = `data:image/jpeg;base64,${data.resultBase64}`;
        } else if (data.resultUrl) {
             resultImg.src = data.resultUrl;
        } else {
             throw new Error('No result returned from API');
        }
        
        // Setup Original for comparison
        const reader = new FileReader();
        reader.onload = (e) => {
            originalImg.src = e.target.result;
            showResult();
        };
        reader.readAsDataURL(files.person);
        
    } catch (err) {
        alert("Error: " + err.message);
        generateBtn.disabled = false;
        loadingOverlay.classList.add('hidden');
    }
});

function showResult() {
    loadingOverlay.classList.add('hidden');
    uploadSection.classList.add('hidden');
    resultSection.classList.remove('hidden');
}

resetBtn.addEventListener('click', () => {
    resultSection.classList.add('hidden');
    uploadSection.classList.remove('hidden');
    generateBtn.disabled = false;
});

downloadBtn.addEventListener('click', () => {
    const a = document.createElement('a');
    a.href = resultImg.src;
    a.download = 'virtual-try-on-result.jpg';
    a.click();
});

// Slider logic
let isSliding = false;
sliderHandle.addEventListener('mousedown', () => isSliding = true);
window.addEventListener('mouseup', () => isSliding = false);
window.addEventListener('mousemove', (e) => {
    if (!isSliding) return;
    const container = document.getElementById('comparison-slider');
    const rect = container.getBoundingClientRect();
    let x = e.clientX - rect.left;
    x = Math.max(0, Math.min(x, rect.width));
    const percent = (x / rect.width) * 100;
    
    sliderHandle.style.left = `${percent}%`;
    originalClip.style.clipPath = `polygon(0 0, ${percent}% 0, ${percent}% 100%, 0 100%)`;
});

// Touch support for slider
sliderHandle.addEventListener('touchstart', () => isSliding = true);
window.addEventListener('touchend', () => isSliding = false);
window.addEventListener('touchmove', (e) => {
    if (!isSliding) return;
    const container = document.getElementById('comparison-slider');
    const rect = container.getBoundingClientRect();
    let x = e.touches[0].clientX - rect.left;
    x = Math.max(0, Math.min(x, rect.width));
    const percent = (x / rect.width) * 100;
    
    sliderHandle.style.left = `${percent}%`;
    originalClip.style.clipPath = `polygon(0 0, ${percent}% 0, ${percent}% 100%, 0 100%)`;
});
