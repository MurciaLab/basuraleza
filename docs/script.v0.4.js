let fileQueue = [];
let successCount = 0;
let failCount = 0;
let totalCount = 0;
let errors = [];
let validFileQueue = []; // Array to track valid files for upload

const googleScriptUrl = "https://api-basuraleza.luistt.es/";

function gpsToDecimal(gpsData, ref) {
    if (!Array.isArray(gpsData) || gpsData.length !== 3) return null;

    const [degrees, minutes, seconds] = gpsData;
    let decimal = degrees + minutes / 60 + seconds / 3600;
    if (ref === "S" || ref === "W") {
        decimal = -decimal;
    }
    return decimal;
}

function isValidGPS(lat, lon, latRef, lonRef) {
    const decimalLat = gpsToDecimal(lat, latRef);
    const decimalLon = gpsToDecimal(lon, lonRef);

    return (
        typeof decimalLat === "number" &&
        typeof decimalLon === "number" &&
        !isNaN(decimalLat) && !isNaN(decimalLon) &&
        decimalLat !== 0 && decimalLon !== 0 &&
        decimalLat >= -90 && decimalLat <= 90 &&
        decimalLon >= -180 && decimalLon <= 180
    );
}


document.getElementById("infoBtn").addEventListener("click", function() {
    document.getElementById("infoModal").style.display = "flex";
});

document.getElementById("helpBtn").addEventListener("click", function() {
    document.getElementById("helpModal").style.display = "flex";
});

function closeModal(id) {
    document.getElementById(id).style.display = "none";
}

window.closeModal = closeModal;

// Enable the upload button only when files are selected
document.getElementById('fileInput').addEventListener('change', async function () {
    const thumbnails = document.getElementById("thumbnails");
    thumbnails.innerHTML = "";
    fileQueue = Array.from(this.files);

    if (fileQueue.length === 0) {
        document.getElementById("uploadBtn").disabled = true;
        return;
    }

    const checkGPSPromises = fileQueue.map((file, index) => checkGPSData(file, index));
    await Promise.all(checkGPSPromises);

    document.getElementById("uploadBtn").disabled = validFileQueue.length === 0;

    // Show delete buttons only if files are selected
    document.querySelectorAll('.delete-btn').forEach(button => {
        button.style.display = 'inline-block'; // Show delete buttons
    });
});

async function checkGPSData(file, index) {
    return new Promise((resolve) => {
        const reader = new FileReader();
        reader.onload = function (e) {
            const container = document.createElement("div");
            container.className = "thumbnail-container";
            container.innerHTML = `
                <img src="${e.target.result}" class="thumbnail" alt="Thumbnail">
                <div class="info">
                    <div class="progressBar" id="progressBar-${index}">
                        <div class="progressFill" id="progressFill-${index}"></div>
                    </div>
                    <div class="error" id="error-${index}"></div>
                    <div class="checkmark" id="checkmark-${index}">Foto válida. Lista para ser subida</div>
                    <div class="success-message" id="successMessage-${index}">✔ ¡Foto subida!</div>
                </div>
            `;
            document.getElementById("thumbnails").appendChild(container);

            EXIF.getData(file, function () {
                const lat = EXIF.getTag(this, "GPSLatitude");
                const lon = EXIF.getTag(this, "GPSLongitude");
                const latRef = EXIF.getTag(this, "GPSLatitudeRef");
                const lonRef = EXIF.getTag(this, "GPSLongitudeRef");


                const datetimeOriginal = EXIF.getTag(this, "DateTimeOriginal");
                file.datetimeOriginal = datetimeOriginal;  // Attach it to the file object
    
                if (!isValidGPS(lat, lon, latRef, lonRef)) {
                    // Mark as invalid photo
                    document.getElementById(`error-${index}`).innerHTML = `
                        <div class="error-message">
                            ❌ Esta foto no se subirá. Falta ubicación GPS
                            <p><a href="https://support.google.com/photos/answer/9921876?sjid=17219850777604204969-EU#zippy" target="_blank">
                                Como activar la ubicación
                            </a></p>
                        </div>
                    `;

                    document.getElementById(`progressBar-${index}`).style.display = "none";
                    failCount++;
                    const errorContainer = document.getElementById(`error-${index}`);
                    errorContainer.style.display = "flex";
                    errorContainer.style.alignItems = "center";
                    errorContainer.style.justifyContent = "space-between";
                    errorContainer.style.gap = "10px";

                    const deleteIcon = document.createElement('img');
                    deleteIcon.src = 'images/bin.png';
                    deleteIcon.alt = 'Eliminar';
                    deleteIcon.className = 'delete-icon';
                    deleteIcon.onclick = () => removeImage(file, index);

                    errorContainer.appendChild(deleteIcon);
                } else {
                    // Mark as valid photo
                    validFileQueue.push(file);
                    document.getElementById(`checkmark-${index}`).style.display = "block";

                    // Create and append the delete button only for valid photos
                    const checkmark = document.getElementById(`checkmark-${index}`);
                    checkmark.style.display = "flex";
                    checkmark.style.alignItems = "center";
                    checkmark.style.justifyContent = "space-between";
                    checkmark.style.gap = "10px";

                    const deleteIcon = document.createElement('img');
                    deleteIcon.src = 'images/bin.png';
                    deleteIcon.alt = 'Eliminar';
                    deleteIcon.className = 'delete-icon';
                    deleteIcon.onclick = () => removeImage(file, index);

                    checkmark.appendChild(deleteIcon);

                }

                // Enable/disable the "Subir" button based on valid files count
                document.getElementById("uploadBtn").disabled = validFileQueue.length === 0;

                resolve();
            });
        };
        reader.readAsDataURL(file);
    });
}


function removeImage(file, index) {
    // Get the delete button's parent container (thumbnail container)
    const thumbnailContainer = event.target.closest('.thumbnail-container');

    // Add the fade-out class to trigger the animation on the specific row
    thumbnailContainer.classList.add('fade-out');

    // Set a timeout to wait until the animation is done (500ms matches the CSS transition duration)
    setTimeout(() => {
        // Remove the image from the fileQueue
        fileQueue.splice(index, 1);

        // Also remove from the validFileQueue if it exists
        validFileQueue = validFileQueue.filter((validFile) => validFile !== file);

        // Remove the thumbnail container from the DOM after the fade-out effect
        thumbnailContainer.remove();

        // Enable/disable the upload button based on valid file count
        document.getElementById("uploadBtn").disabled = validFileQueue.length === 0;
    }, 500);  // Match the duration of the fade-out transition (500ms)

    document.getElementById("uploadBtn").disabled = validFileQueue.length === 0;

}

// Upload the images when the button is clicked
document.getElementById("uploadBtn").addEventListener("click", async function () {
    document.getElementById("uploadBtn").disabled = true;
    document.getElementById("fileInput").disabled = true;

    successCount = 0;
    failCount = 0;
    errors = [];
    validFileQueue = [];  // Clear previous valid files for the upload

    const uploadPromises = fileQueue.map((file, index) => uploadFile(file, index));
    await Promise.all(uploadPromises);

    // After the upload, clear the file input and disable the button to prevent double submission
    document.getElementById("fileInput").value = "";
    document.getElementById("uploadBtn").disabled = true;  // Disable the upload button after submission

    // Re-enable the file input for new selection and clear previous photos
    document.getElementById("fileInput").disabled = false;
});

document.getElementById("uploadBtn").addEventListener("click", function () {
    document.querySelectorAll('.delete-btn').forEach(button => {
        button.style.display = 'none'; // Hide all delete buttons after upload
    });
});

async function uploadFile(file, index) {
    return new Promise((resolve) => {
        EXIF.getData(file, async function () {
            const lat = EXIF.getTag(this, "GPSLatitude");
            const lon = EXIF.getTag(this, "GPSLongitude");
            const latRef = EXIF.getTag(this, "GPSLatitudeRef");
            const lonRef = EXIF.getTag(this, "GPSLongitudeRef");
            const datetimeOriginal = EXIF.getTag(this, "DateTimeOriginal");

            if (!isValidGPS(lat, lon, latRef, lonRef)) {
                failCount++;
                errors.push(`${file.name}: Missing GPS data`);
                document.getElementById(`error-${index}`).innerHTML = `
                        <div class="error-message">
                            ❌ Foto sin subir. Falta ubicación GPS
                            <p><a href="https://support.google.com/photos/answer/9921876?sjid=17219850777604204969-EU#zippy" target="_blank">
                                Como activar la ubicación
                            </a></p>
                        </div>
                    `;
                document.getElementById(`progressBar-${index}`).style.display = "none"; // Hide the progress bar if no GPS data
                resolve();
                return;
            }

            validFileQueue.push(file); // Add valid file to the validFileQueue

            const compressedFile = await resizeAndCompressImagePreservingExif(file, 1024);
            const reader = new FileReader();

            // Set the name manually if it's missing
            const fileName = file.name || "untitled.jpg"; // Use a default name if the original file name is missing

            reader.readAsDataURL(compressedFile);
            reader.onload = async function () {
                let base64String = reader.result.split(',')[1];
                let data = new FormData();
                data.append("file", base64String);
                data.append("filename", fileName);  // Use the manually set file name here
                data.append("mimeType", compressedFile.type);

                if (datetimeOriginal) {
                    data.append("exifDate", datetimeOriginal);
                }

                let progressFill = document.getElementById(`progressFill-${index}`);
                document.getElementById(`progressBar-${index}`).style.display = "block"; // Show progress bar when upload starts
                progressFill.style.width = "10%";

                // Hide the "valid photo" message once the upload begins
                document.getElementById(`checkmark-${index}`).style.display = "none";

                try {
                    let response = await fetch(googleScriptUrl, { method: "POST", body: data });
                    let result = await response.json();

                    if (result.status === "success") {
                        successCount++;
                        progressFill.style.width = "100%";
                        // Show success message after upload is complete
                        document.getElementById(`checkmark-${index}`).innerHTML = "✔ ¡Foto subida!";
                        document.getElementById(`checkmark-${index}`).style.color = "#8AAA41"; // Green color for success
                        document.getElementById(`checkmark-${index}`).style.display = "block"; // Show the success message
                        setTimeout(() => {
                            document.getElementById(`progressBar-${index}`).style.display = "none"; // Hide the progress bar after successful upload
                        }, 500);
                    } else {
                        failCount++;
                        errors.push(`${file.name}: ${result.message}`);
                        document.getElementById(`error-${index}`).innerText = `❌ ${result.message}`;
                    }
                } catch (error) {
                    failCount++;
                    errors.push(`${file.name}: Network error`);
                    document.getElementById(`error-${index}`).innerText = "❌ Error de red";
                }

                resolve();
            };
        });
    });
}


function resizeAndCompressImage(file, maxSize) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        const reader = new FileReader();

        reader.onload = function (event) {
            img.src = event.target.result;
        };

        img.onload = function () {
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');

            let width = img.width;
            let height = img.height;

            if (width > height) {
                if (width > maxSize) {
                    height *= maxSize / width;
                    width = maxSize;
                }
            } else {
                if (height > maxSize) {
                    width *= maxSize / height;
                    height = maxSize;
                }
            }

            canvas.width = width;
            canvas.height = height;
            ctx.drawImage(img, 0, 0, width, height);

            canvas.toBlob(function (blob) {
                resolve(blob);
            }, file.type, 0.7);
        };

        reader.readAsDataURL(file);
    });
}

function resizeAndCompressImagePreservingExif(file, maxSize) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();

        reader.onload = function (event) {
            const originalDataURL = event.target.result;

            // Extract EXIF from original
            let exifObj = piexif.load(originalDataURL);
            let exifBytes = piexif.dump(exifObj);

            const img = new Image();
            img.src = originalDataURL;

            img.onload = function () {
                const canvas = document.createElement('canvas');
                const ctx = canvas.getContext('2d');

                let width = img.width;
                let height = img.height;

                if (width > height) {
                    if (width > maxSize) {
                        height *= maxSize / width;
                        width = maxSize;
                    }
                } else {
                    if (height > maxSize) {
                        width *= maxSize / height;
                        height = maxSize;
                    }
                }

                canvas.width = width;
                canvas.height = height;
                ctx.drawImage(img, 0, 0, width, height);

                const compressedDataURL = canvas.toDataURL(file.type, 0.7);

                // Insert EXIF back into the new DataURL
                const newDataURLWithExif = piexif.insert(exifBytes, compressedDataURL);

                // Convert DataURL back to Blob
                const byteString = atob(newDataURLWithExif.split(',')[1]);
                const mimeString = newDataURLWithExif.split(',')[0].split(':')[1].split(';')[0];

                const ab = new ArrayBuffer(byteString.length);
                const ia = new Uint8Array(ab);
                for (let i = 0; i < byteString.length; i++) {
                    ia[i] = byteString.charCodeAt(i);
                }

                const newBlob = new Blob([ab], { type: mimeString });
                resolve(newBlob);
            };
        };

        reader.readAsDataURL(file);
    });
}
