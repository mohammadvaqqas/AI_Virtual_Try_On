import os
import base64
import tempfile
import traceback
import requests
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
from PIL import Image
from gradio_client import Client, handle_file

load_dotenv(override=True)

app = Flask(__name__)
CORS(app)

print("Initialized Hugging Face API Integration.")


def save_temp_image_from_file(file_storage, max_size=None):
    """Save uploaded file to a temp JPEG. Preserves original dimensions by default."""
    fd, path = tempfile.mkstemp(suffix=".jpg")
    img = Image.open(file_storage)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    # Only resize if max_size is explicitly requested
    if max_size:
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
    img.save(path, format="JPEG", quality=95)
    os.close(fd)
    return path


def save_temp_image_from_path(src_path):
    """Copy image from path to a temp JPEG. Preserves original dimensions."""
    fd, path = tempfile.mkstemp(suffix=".jpg")
    img = Image.open(src_path)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    img.save(path, format="JPEG", quality=95)
    os.close(fd)
    return path


def get_image_dimensions(image_path):
    """Get the dimensions of an image file."""
    with Image.open(image_path) as img:
        return img.size  # (width, height)


def resize_to_match(image_path, target_width, target_height):
    """Resize an image to match the target dimensions, preserving quality."""
    fd, path = tempfile.mkstemp(suffix=".jpg")
    img = Image.open(image_path)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    # Resize to match original dimensions
    img_resized = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
    img_resized.save(path, format="JPEG", quality=95)
    os.close(fd)
    return path


def download_image(url):
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(path, 'wb') as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
        return path
    else:
        raise Exception(f"Failed to download generated image: {response.text}")


def call_idmvton_api(person_img_path, garment_img_path):
    """Call IDM-VTON for upper-body garment try-on."""
    try:
        hf_token = os.getenv("HF_TOKEN") or None
        client = Client("yisol/IDM-VTON", token=hf_token)

        # Prepare person image payload per Gradio ImageEditor spec
        person_dict = {
            "background": handle_file(person_img_path),
            "layers": [],
            "composite": None
        }

        # Predict using IDM-VTON endpoint
        result = client.predict(
            dict=person_dict,
            garm_img=handle_file(garment_img_path),
            garment_des="A stylish upper-body garment",
            is_checked=True,         # Auto-masking enabled
            is_checked_crop=False,   # Auto-crop disabled
            denoise_steps=30,
            seed=42,
            api_name="/tryon"
        )

        # Result returns a tuple of (output_img_path, masked_img_path)
        output_image_path = result[0]
        return save_temp_image_from_path(output_image_path)

    except Exception as e:
        raise Exception(f"IDM-VTON API Error: {str(e)}")


def extract_image_path(result_item):
    """Extract the actual file path from a Gradio gallery result item.
    
    Gallery items can be:
    - A plain string (filepath)
    - A dict like {'image': path, 'caption': ...} or {'path': path} or {'name': path}
    - A tuple like (path, caption)
    - A list like [path, caption]
    """
    if isinstance(result_item, str):
        return result_item
    elif isinstance(result_item, dict):
        # Try common Gradio gallery dict keys
        for key in ['image', 'path', 'name', 'url']:
            if key in result_item and result_item[key]:
                return result_item[key]
        # If none of the known keys, try the first string value
        for val in result_item.values():
            if isinstance(val, str) and (os.path.exists(val) or val.startswith('http')):
                return val
        raise Exception(f"Could not extract image path from dict: {result_item}")
    elif isinstance(result_item, (list, tuple)) and len(result_item) > 0:
        return extract_image_path(result_item[0])
    else:
        raise Exception(f"Unexpected result format: {type(result_item)} - {result_item}")


def call_ootd_api(person_img_path, garment_img_path, category):
    """Call OOTDiffusion for full-body garment try-on (upper/lower/dress).
    
    Args:
        person_img_path: Path to person image
        garment_img_path: Path to garment image
        category: "Upper-body", "Lower-body", or "Dress"
    """
    try:
        hf_token = os.getenv("HF_TOKEN") or None
        client = Client("levihsu/OOTDiffusion", token=hf_token)

        
        result = client.predict(
            handle_file(person_img_path),  
            handle_file(garment_img_path),  
            category,                       
            1,                              
            20,                             
            2.0,                            
            42,                             
            api_name="/process_dc"
        )

        # Log raw result for debugging
        print(f"OOTDiffusion raw result type: {type(result)}")
        print(f"OOTDiffusion raw result: {result}")

        # Extract image path from gallery result
        if isinstance(result, (list, tuple)) and len(result) > 0:
            output_image_path = extract_image_path(result[0])
        elif isinstance(result, dict):
            output_image_path = extract_image_path(result)
        elif isinstance(result, str):
            output_image_path = result
        else:
            raise Exception(f"Unexpected result format from OOTDiffusion: {type(result)}")

        print(f"Extracted output image path: {output_image_path}")

        
        if output_image_path.startswith('http'):
            return download_image(output_image_path)
        else:
            return save_temp_image_from_path(output_image_path)

    except Exception as e:
        raise Exception(f"OOTDiffusion API Error: {str(e)}")


def path_to_base64(path):
    with open(path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/try-on', methods=['POST'])
def try_on():
    if 'person_image' not in request.files:
        return jsonify({"error": "Missing person_image"}), 400
        
    person_file = request.files['person_image']
    upper_file = request.files.get('upper_image')
    lower_file = request.files.get('lower_image')
    
    if not upper_file and not lower_file:
        return jsonify({"error": "Provide at least one garment (upper or lower)"}), 400

    temp_files = []

    try:
        # Save person image - preserve original dimensions
        current_person_path = save_temp_image_from_file(person_file)
        temp_files.append(current_person_path)
        
        # Store original dimensions to restore later
        original_width, original_height = get_image_dimensions(current_person_path)
        print(f"Original person image dimensions: {original_width}x{original_height}")
        
        # --- UPPER BODY: Use IDM-VTON (best for shirts/tops) ---
        if upper_file:
            print("Processing Upper Garment via IDM-VTON...")
            upper_path = save_temp_image_from_file(upper_file)
            temp_files.append(upper_path)
            
            output_path = call_idmvton_api(current_person_path, upper_path)
            temp_files.append(output_path)
            
            # Resize output back to original dimensions to prevent shrinking
            resized_path = resize_to_match(output_path, original_width, original_height)
            temp_files.append(resized_path)
            current_person_path = resized_path
            print(f"Upper garment applied. Output resized to {original_width}x{original_height}")
            
        # --- LOWER BODY: Use OOTDiffusion (supports lower-body category) ---
        if lower_file:
            print("Processing Lower Garment via OOTDiffusion (Lower-body)...")
            lower_path = save_temp_image_from_file(lower_file)
            temp_files.append(lower_path)
            
            output_path = call_ootd_api(current_person_path, lower_path, "Lower-body")
            temp_files.append(output_path)
            
            # Resize output back to original dimensions to prevent shrinking
            resized_path = resize_to_match(output_path, original_width, original_height)
            temp_files.append(resized_path)
            current_person_path = resized_path
            print(f"Lower garment applied. Output resized to {original_width}x{original_height}")
            
        print("Try-on completed successfully.")
        result_b64 = path_to_base64(current_person_path)
        
        return jsonify({"resultBase64": result_b64}), 200
        
    except Exception as e:
        traceback.print_exc()
        print(f"Error during try-on processing: {str(e)}")
        return jsonify({"error": str(e)}), 500
        
    finally:
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except BaseException:
                pass

if __name__ == '__main__':
    app.run(debug=True, port=5000)
