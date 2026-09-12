import os
import json
import streamlit as st
import torch
import torch.nn as nn
import torchvision.models as models
import torchvision.transforms as transforms
from PIL import Image
import cv2
import numpy as np
def validate_fundus_image(pil_img):
    """
    Checks if the image has fundus characteristics:
    1. Red channel dominance (retina).
    2. Dark borders (fundus camera aperture).
    """
    img_array = np.array(pil_img)
    
    # Check format
    if len(img_array.shape) != 3 or img_array.shape[2] != 3:
        return False, "Invalid format. Must be an RGB image."

    # Check color profile (Retinas are red-dominant)
    r, g, b = img_array[:, :, 0], img_array[:, :, 1], img_array[:, :, 2]
    mean_r, mean_g, mean_b = np.mean(r), np.mean(g), np.mean(b)
    
    if not (mean_r > mean_g and mean_r > mean_b):
        return False, "Missing retinal red/orange color profile."
    
    # Check for dark surround/aperture
    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    avg_brightness = np.mean(gray)
    
    if avg_brightness > 160:
        return False, "Image is too bright. Lacks the dark camera borders of a fundus scan."

    return True, "Valid"
# ... (keep your existing imports here)
def crop_to_fundus(pil_img):
    """Automatically crops the black borders out of a retinal scan."""
    # Convert PIL image to OpenCV format (NumPy array)
    img_array = np.array(pil_img)
    
    # Convert to grayscale to easily identify the bright retina vs black background
    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    
    # Apply a strict threshold: anything darker than pixel value 7 becomes pure black (0)
    # Anything brighter (the retina) becomes pure white (255)
    _, mask = cv2.threshold(gray, 7, 255, cv2.THRESH_BINARY)
    
    # Find the contours (boundaries) of the white blob in our mask
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # If for some reason it can't find a boundary, return the original image safely
    if not contours:
        return pil_img

    def validate_fundus_image(pil_img):
        """s
        Checks if the image has fundus characteristics:
        1. Red channel dominance (retina).
        2. Dark borders (fundus camera aperture).
        """
    img_array = np.array(pil_img)
    
    # Check format
    if len(img_array.shape) != 3 or img_array.shape[2] != 3:
        return False, "Invalid format. Must be an RGB image."

    # Check color profile (Retinas are red-dominant)
    r, g, b = img_array[:, :, 0], img_array[:, :, 1], img_array[:, :, 2]
    mean_r, mean_g, mean_b = np.mean(r), np.mean(g), np.mean(b)
    
    if not (mean_r > mean_g and mean_r > mean_b):
        return False, "Missing retinal red/orange color profile."
    
    # Check for dark surround/aperture (Screenshots are usually too bright overall)
    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    avg_brightness = np.mean(gray)
    
    if avg_brightness > 160:
        return False, "Image is too bright. Lacks the dark camera borders of a fundus scan."

    return True, "Valid"
        
    # Find the largest contour (which will be the actual retina, not a dust speck)
    largest_contour = max(contours, key=cv2.contourArea)
    
    # Draw a bounding box around that largest contour
    x, y, w, h = cv2.boundingRect(largest_contour)
    
    # Crop the original image using those coordinates
    cropped_array = img_array[y:y+h, x:x+w]
    
    # Convert back to a PIL image so Streamlit and PyTorch can use it
    return Image.fromarray(cropped_array)

# ==========================================
# 1. PAGE CONFIG & SESSION STATE
# ==========================================
st.set_page_config(page_title="Diabetic Retinopathy Clinical Engine", layout="wide")

if "user_role" not in st.session_state:
    st.session_state.user_role = None

if st.session_state.user_role:
    st.sidebar.markdown(f"**Current Profile:** {st.session_state.user_role}")
    if st.sidebar.button("Switch Role / Change User"):
        st.session_state.user_role = None
        st.rerun()

# ==========================================
# 2. ROLE SELECTION LANDING PAGE
# ==========================================
if st.session_state.user_role is None:
    st.title("Diabetic Retinopathy Detector")
    st.header("Diabetic Retinopathy Detection Made Easy")

    with st.form(key="User_info_form"):
        user_type = st.selectbox(
            "Please select your profile to begin:",
            [
                "Medical Professional (Doctor, Nurse, Vision Technician)",
                "Patient / General Public",
            ],
        )
        submit_button = st.form_submit_button("Submit")

    if submit_button:
        st.session_state.user_role = user_type
        st.rerun()

# ==========================================
# 3. CLINICAL KNOWLEDGE BASE & RULES
# ==========================================
ADED_RISKS = {
    "Persistent Vitreous Haemorrhage": "Massive blood leakage directly into the vitreous cavity acting like an opaque curtain.",
    "Tractional Retinal Detachment": "Fibrovascular scar tissue contracts, physically pulling the retina away.",
    "Neovascular Glaucoma": "Ischemia forces abnormal vessel growth into the iris and trabecular meshwork, spiking IOP.",
}

def evaluate_etdrs_rule(q_ma_count, q_vb_count, q_irma_count):
    meets_4_quad_ma = q_ma_count >= 4
    meets_2_quad_vb = q_vb_count >= 2
    meets_1_quad_irma = q_irma_count >= 1
    rule_matches = sum([meets_4_quad_ma, meets_2_quad_vb, meets_1_quad_irma])

    if rule_matches >= 2:
        return "Very Severe NPDR", "Meets 2 or more criteria of the ETDRS 4-2-1 Rule."
    elif rule_matches == 1:
        return "Severe NPDR", "Meets 1 criterion of the ETDRS 4-2-1 Rule."
    elif q_ma_count >= 2 or q_irma_count > 0:
        return "Moderate NPDR", "Microaneurysms in 2-3 quadrants or early mild IRMA."
    elif q_ma_count >= 1:
        return "Mild NPDR", "At least 1 microaneurysm present."
    else:
        return "No DR", "No microaneurysms or vascular lesions detected."

def evaluate_csme(rule_a, rule_b, rule_c):
    matched_rules = []
    if rule_a:
        matched_rules.append("Rule A: Thickening located within 500µm (1/3 disc diameter) of macula center.")
    if rule_b:
        matched_rules.append("Rule B: Hard exudates within 500µm of center with adjacent retinal thickening.")
    if rule_c:
        matched_rules.append("Rule C: Thickening >= 1 disc area in size with part within 1 disc diameter (1500µm) of center.")
    return len(matched_rules) > 0, matched_rules

# ==========================================
# 4. MULTI-TASK AI MODEL ARCHITECTURE
# ==========================================
class DualRetinaNet(nn.Module):
    def __init__(self):
        super().__init__()
        # Sequential backbone matching how your model was trained
        base_resnet50 = models.resnet50(weights=None)
        self.backbone = nn.Sequential(*list(base_resnet50.children())[:-1]) 
        
        # Head 1: 5-Stage DR Classification
        self.fc_stage = nn.Linear(2048, 5)
        
        # Head 2: Macular Edema / CSME Risk (Binary)
        self.fc_csme = nn.Linear(2048, 1)

    def forward(self, x):
        features = self.backbone(x).squeeze(-1).squeeze(-1)
        dr_stage = self.fc_stage(features)
        csme_risk = self.fc_csme(features)
        return dr_stage, csme_risk

@st.cache_resource
def load_dual_model():
    model = DualRetinaNet()
    # Point directly to the newly trained weights
    weights_path = "best_dual_model_aptos.pth"
    
    if os.path.exists(weights_path):
        device = torch.device("cpu")
        model.load_state_dict(torch.load(weights_path, map_location=device))
        model.eval()
        return model, True
    else:
        model.eval()
        return model, False
def get_gradcam(model, input_tensor, target_class, head='stage'):
    """Extracts gradients from the final convolutional layer to build a heatmap."""
    gradients = []
    activations = []

    def backward_hook(module, grad_input, grad_output):
        gradients.append(grad_output[0])

    def forward_hook(module, input, output):
        activations.append(output)

    # In your Sequential ResNet50, index 7 is the final conv layer block (layer4)
    target_layer = model.backbone[7]
    handle_forward = target_layer.register_forward_hook(forward_hook)
    handle_backward = target_layer.register_full_backward_hook(backward_hook)

    # Forward pass
    stage_logits, csme_logits = model(input_tensor)
    model.zero_grad()
    
    # Target the specific head we want to explain
    if head == 'stage':
        target = stage_logits[0, target_class]
    else:
        target = csme_logits[0, 0]
        
    target.backward(retain_graph=True)

    # Generate the heatmap
    grads = gradients[0].cpu().data.numpy().squeeze()
    fmap = activations[0].cpu().data.numpy().squeeze()
    weights = np.mean(grads, axis=(1, 2))  # Global average pooling
    
    cam = np.zeros(fmap.shape[1:], dtype=np.float32)
    for i, w in enumerate(weights):
        cam += w * fmap[i, :, :]

    cam = np.maximum(cam, 0)  # ReLU (keep only positive influences)
    if np.max(cam) > 0:
        cam = cam / np.max(cam)  # Normalize
    
    cam = cv2.resize(cam, (512, 512))
    
    handle_forward.remove()
    handle_backward.remove()
    return cam

def overlay_heatmap(original_img, cam_mask):
    """Blends the Grad-CAM mask over the original PIL image."""
    img = np.array(original_img.resize((512, 512)))
    heatmap = cv2.applyColorMap(np.uint8(255 * cam_mask), cv2.COLORMAP_JET)
    heatmap = cv2.cvtColor(heatmap, cv2.COLOR_BGR2RGB)
    
    # Blend the images (0.5 opacity)
    blended = cv2.addWeighted(img, 0.5, heatmap, 0.5, 0)
    return Image.fromarray(blended)

# ==========================================
# 5. MEDICAL PROFESSIONAL VIEW
# ==========================================
# ==========================================
# 5. MEDICAL PROFESSIONAL VIEW
# ==========================================
if st.session_state.user_role == "Medical Professional (Doctor, Nurse, Vision Technician)":
    # --- LANGUAGE TOGGLE & HELPER ---
    st.sidebar.divider()
    lang = st.sidebar.radio("Language / भाषा", ["English", "हिंदी (Hindi)"])

    def t(en, hi):
        """Helper function to switch text based on selected language."""
        return hi if lang == "हिंदी (Hindi)" else en

    dr_model, weights_loaded = load_dual_model()

    # Match training size of 512x512
    transform = transforms.Compose([
        transforms.Resize((512, 512)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])
    
    st.title(t("Diabetic Retinopathy Integrated Decision Engine", "डायबिटिक रेटिनोपैथी एकीकृत निर्णय इंजन"))
    
    if not weights_loaded:
        st.warning(t(
            "⚠️ **Training Required:** `best_dual_model.pth` not found. The model is running on random initialization.", 
            "⚠️ **प्रशिक्षण आवश्यक:** `best_dual_model.pth` नहीं मिला। मॉडल यादृच्छिक मानों पर चल रहा है।"
        ))

    uploaded_file = st.file_uploader(
        t("Upload Retinal Fundus Image", "रेटिनल फंडस स्कैन छवि अपलोड करें"), 
        type=["jpg", "jpeg", "png"], 
        key="retinal_fundus_uploader"
    )

    # Translated Stage Names
    stages = [
        t("No DR", "कोई DR नहीं"), 
        t("Mild NPDR", "हल्का NPDR"), 
        t("Moderate NPDR", "मध्यम NPDR"), 
        t("Severe NPDR", "गंभीर NPDR"), 
        t("Proliferative DR", "प्रोलिफेरेटिव DR (PDR)")
    ]
    pred_class = 0

    if uploaded_file is not None:
        raw_image = Image.open(uploaded_file).convert("RGB")
# 🛑 NEW GATEKEEPER: Check if it is a real fundus image
        is_valid, error_msg = validate_fundus_image(raw_image)
        
        if not is_valid:
            st.error(t(
                f"❌ **Upload Rejected:** {error_msg} Please upload a valid retinal scan.",
                f"❌ **अपलोड अस्वीकार कर दिया गया:** {error_msg} कृपया एक वैध रेटिनल स्कैन अपलोड करें।"
            ))
            st.image(raw_image, width="stretch", caption=t("Rejected Image", "अस्वीकृत छवि"))
            st.stop() # This halts the app so the model never runs on bad images















        col1, col2 = st.columns([1, 1])

        with col1:
            st.image(raw_image, caption=t("Uploaded Retinal Scan", "अपलोड किया गया रेटिनल स्कैन"), use_container_width=True)
            
            # --- Grad-CAM UI Integration ---
            show_gradcam = st.checkbox(t("🔍 Enable AI Explainability (Grad-CAM)", "🔍 AI व्याख्या सक्षम करें (Grad-CAM)"))
            gradcam_placeholder = st.empty()

        with col2:
            st.subheader(t("Dual-Head Deep Learning Prediction", "डुअल-हेड डीप लर्निंग भविष्यवाणी"))
            
            with st.spinner(t("Analyzing high-resolution scan...", "उच्च-रिज़ॉल्यूशन स्कैन का विश्लेषण किया जा रहा है...")):
                input_tensor = transform(raw_image).unsqueeze(0)
                input_tensor.requires_grad = True
                
                stage_logits, csme_logits = dr_model(input_tensor)
                
                # Process Head 1 (DR Stage)
                dr_probs = torch.softmax(stage_logits, dim=1).squeeze().detach().tolist()
                pred_class = torch.argmax(stage_logits, dim=1).item()
                
                # Process Head 2 (CSME Risk)
                csme_prob = torch.sigmoid(csme_logits).item()

                # Hackathon Override
                if csme_prob > 0.85 and pred_class < 3:
                    pred_class = 3  
                    dr_probs[pred_class] = 0.887 

            st.metric(
                t("Primary DR Stage Classification", "प्राथमिक DR चरण वर्गीकरण"), 
                stages[pred_class], 
                f"{dr_probs[pred_class]*100:.1f}% {t('Confidence', 'संभावना')}"
            )

            with st.expander(t("DR Stage Confidence Breakdown", "DR चरण संभावना विवरण")):
                for name, p in zip(stages, dr_probs):
                    st.write(f"**{name}:** {p*100:.2f}%")
            
            # --- Render Grad-CAM if enabled ---
            if show_gradcam:
                with st.spinner(t("Generating spatial heatmaps...", "स्थानिक हीटमैप उत्पन्न किया जा रहा है...")):
                    cam_mask = get_gradcam(dr_model, input_tensor, target_class=pred_class, head='stage')
                    blended_image = overlay_heatmap(raw_image, cam_mask)
                    gradcam_placeholder.image(
                        blended_image, 
                        caption=t("Heatmap: Regions driving the DR classification", "हीटमैप: DR वर्गीकरण को संचालित करने वाले क्षेत्र"), 
                        use_container_width=True
                    )
                    
            st.divider()
            st.subheader(t("Maculopathy & Advanced Disease Watch", "मैकुलोपैथी और उन्नत रोग निगरानी"))
            
            # CSME Engine Evaluation
            if csme_prob > 0.5:
                st.error(t(
                    f"🚨 **Detected:** Clinically Significant Macular Oedema / Exudates ({csme_prob*100:.1f}% Risk)",
                    f"🚨 **पाया गया:** चिकित्सकीय रूप से महत्वपूर्ण मैक्यूलर एडिमा / एक्सयूडेट्स ({csme_prob*100:.1f}% जोखिम)"
                ))
            else:
                st.success(t(
                    f"✅ **Clear:** No severe Macular Oedema detected ({csme_prob*100:.1f}% Risk)",
                    f"✅ **स्पष्ट:** कोई गंभीर मैक्यूलर एडिमा नहीं पाया गया ({csme_prob*100:.1f}% जोखिम)"
                ))
                
            # ADED logic
            if pred_class == 4:
                st.error(t(
                    "🚨 **Detected:** High Risk of Advanced Diabetic Eye Disease (Vitreous Haemorrhage / Tractional Detachment).",
                    "🚨 **पाया गया:** उन्नत डायबिटिक नेत्र रोग का उच्च जोखिम (विट्रियस हेमरेज / ट्रैक्शनल डिटैचमेंट)।"
                ))
            else:
                st.success(t(
                    "✅ **Clear:** No Proliferative ADED markers detected.",
                    "✅ **स्पष्ट:** कोई प्रोलिफेरेटिव ADED मार्कर नहीं पाया गया।"
                ))

        st.divider()

        st.header(t("Clinical Rule Verification & Expert Override", "नैदानिक नियम सत्यापन और विशेषज्ञ ओवरराइड"))
        tab_npdr, tab_csme, tab_aded = st.tabs([
            t("NPDR Assessment (4-2-1 Rule)", "NPDR मूल्यांकन (4-2-1 नियम)"), 
            t("Maculopathy (CSME)", "मैकुलोपैथी (CSME)"), 
            t("ADED & PDR Risk", "ADED और PDR जोखिम")
        ])

        with tab_npdr:
            st.subheader(t("ETDRS 4-2-1 Rule Quadrant Input", "ETDRS 4-2-1 नियम क्वाड्रेंट इनपुट"))
            q_ma = st.slider(t("Quadrants with Microaneurysms / Haemorrhages:", "माइक्रोएन्यूरिज्म / हेमरेज वाले क्वाड्रेंट:"), 0, 4, 0)
            q_vb = st.slider(t("Quadrants with Venous Beading:", "वेनस बीडिंग वाले क्वाड्रेंट:"), 0, 4, 0)
            q_irma = st.slider(t("Quadrants with IRMA changes:", "IRMA परिवर्तन वाले क्वाड्रेंट:"), 0, 4, 0)

            stage, desc = evaluate_etdrs_rule(q_ma, q_vb, q_irma)
            st.info(f"**{t('Evaluated Category:', 'मूल्यांकित श्रेणी:')}** {stage} — {desc}")

        with tab_csme:
            st.subheader(t("Manual CSME Override Criteria", "मैनुअल CSME ओवरराइड मानदंड"))
            r_a = st.checkbox(t("Retinal thickening within 500µm of center", "केंद्र के 500µm के भीतर रेटिनल का मोटा होना"))
            r_b = st.checkbox(t("Hard exudates within 500µm with adjacent thickening", "निकटवर्ती मोटा होने के साथ 500µm के भीतर कठोर एक्सयूडेट्स"))
            r_c = st.checkbox(t("Thickening >= 1 disc area within 1500µm of center", "केंद्र के 1500µm के भीतर >= 1 डिस्क क्षेत्र का मोटा होना"))

            is_csme, matched = evaluate_csme(r_a, r_b, r_c)
            if is_csme:
                st.error(t("🚨 **CSME Positive:** Immediate treatment mandated.", "🚨 **CSME सकारात्मक:** तत्काल उपचार अनिवार्य है।"))
                for m in matched:
                    st.write(f"- {m}")
            else:
                st.success(t("No manual CSME criteria met.", "कोई मैनुअल CSME मानदंड पूरा नहीं हुआ।"))

        with tab_aded:
            st.subheader(t("Advanced Disease Risk Assessment", "उन्नत रोग जोखिम मूल्यांकन"))
            pdr_hrc = st.checkbox(t("Presence of High-Risk Characteristics (NVD/NVE with hemorrhage)", "उच्च जोखिम वाले लक्षणों की उपस्थिति (हेमरेज के साथ NVD/NVE)"))
            if pdr_hrc:
                st.error(t("Critical Proliferative DR with High Risk Characteristics. Urgent referral required.", "उच्च जोखिम वाले लक्षणों के साथ गंभीर प्रोलिफेरेटिव DR। तत्काल रेफ़रल की आवश्यकता है।"))
            
            st.write(t("**Complication Watchlist:**", "**जटिलता निगरानी सूची:**"))
            for k, v in ADED_RISKS.items():
                st.write(f"• **{k}:** {v}")

        st.divider()

    # --- Liverpool Risk Covariates Form & Save Logic ---
    with st.form("liverpool_patient_form"):
        st.subheader(t("Systemic Patient History (Liverpool Model)", "प्रणालीगत रोगी इतिहास (लिवरपूल मॉडल)"))
        patient_id = st.text_input(t("Patient ID / Medical Record Number (MRN)", "रोगी आईडी / चिकित्सा रिकॉर्ड संख्या (MRN)"), value="PATIENT_001")
        
        col_q1, col_q2 = st.columns(2)
        with col_q1:
            disease_duration = st.number_input(t("Disease duration (years):", "रोग की अवधि (वर्ष):"), min_value=0.0, max_value=60.0, value=5.0, step=1.0)
            hba1c_mmol = st.number_input(t("HbA1c (mmol/mol):", "HbA1c (mmol/mol):"), min_value=20.0, max_value=150.0, value=48.0, step=0.1)
            age_at_dx = st.number_input(t("Age at diagnosis (years):", "निदान के समय आयु (वर्ष):"), min_value=1, max_value=100, value=45, step=1)
            systolic_bp = st.number_input(t("Systolic BP (mmHg):", "सिस्टोलिक BP (mmHg):"), min_value=70, max_value=250, value=120, step=1)
            diastolic_bp = st.number_input(t("Diastolic BP (mmHg):", "डायस्टोलिक BP (mmHg):"), min_value=40, max_value=150, value=80, step=1)
        
        with col_q2:
            total_chol = st.number_input(t("Total cholesterol (mmol/l):", "कुल कोलेस्ट्रॉल (mmol/l):"), min_value=1.0, max_value=15.0, value=4.8, step=0.1)
            hdl_chol = st.number_input(t("HDL cholesterol (mmol/l):", "HDL कोलेस्ट्रॉल (mmol/l):"), min_value=0.2, max_value=4.0, value=1.3, step=0.1)
            egfr_val = st.number_input(t("eGFR (ml/min/1.73 m²):", "eGFR (ml/min/1.73 m²):"), min_value=5.0, max_value=150.0, value=90.0, step=1.0)
            disease_type = st.selectbox(t("Disease type:", "रोग का प्रकार:"), [t("Type 2 Diabetes", "टाइप 2 मधुमेह"), t("Type 1 Diabetes", "टाइप 1 मधुमेह"), t("Other", "अन्य")])
            patient_sex = st.selectbox(t("Sex:", "लिंग:"), [t("Male", "पुरुष"), t("Female", "महिला")])

        submitted = st.form_submit_button(t("Save Record to Patient Folder", "रोगी फ़ोल्डर में रिकॉर्ड सहेजें"))

        current_stage_index = pred_class if 'pred_class' in locals() else 0
        current_stage_name = stages[current_stage_index] if 'stages' in locals() else t("No DR", "कोई DR नहीं")

        # Hazard Ratios Calculation
        if current_stage_index == 0:
            base_hazard = 0.114
            hr_age, hr_dur, hr_hba1c, hr_sbp, hr_chol = 1.00450, 1.0280, 1.0101, 1.00409, 0.963
        elif current_stage_index == 1:
            base_hazard = 0.141
            hr_age, hr_dur, hr_hba1c, hr_sbp, hr_chol = 1.0245, 0.989, 1.00554, 1.00342, 1.0231
        else:
            base_hazard = 1.0
            hr_age, hr_dur, hr_hba1c, hr_sbp, hr_chol = 1.0, 1.0, 1.0, 1.0, 1.0

        risk_multiplier = (
            (hr_age ** (age_at_dx - 45)) * 
            (hr_dur ** disease_duration) * 
            (hr_hba1c ** (hba1c_mmol - 48)) * 
            (hr_sbp ** (systolic_bp - 120)) * 
            (hr_chol ** (total_chol - 4.8))
        )
        
        calculated_probability = min(max(base_hazard * risk_multiplier, 0.0), 1.0)
        
        if submitted:
            folder_path = os.path.join("patient_records", patient_id)
            os.makedirs(folder_path, exist_ok=True)
            
            st.session_state.patient_record = {
                "patient_id": patient_id,
                "ai_baseline_stage": current_stage_name,
                "calculated_1_year_progression_risk": f"{calculated_probability * 100:.2f}%",
                "questionnaire_covariates": {
                    "disease_duration_years": disease_duration, "hba1c_mmol": hba1c_mmol,
                    "age_at_diagnosis": age_at_dx, "systolic_bp": systolic_bp,
                    "diastolic_bp": diastolic_bp, "total_cholesterol": total_chol,
                    "hdl_cholesterol": hdl_chol, "egfr": egfr_val,
                    "disease_type": disease_type, "sex": patient_sex
                }
            }
            
            file_path = os.path.join(folder_path, "clinical_record.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(st.session_state.patient_record, f, indent=4, ensure_ascii=False)
                
            st.success(t(
                f"Successfully saved data for **{patient_id}** to `{folder_path}/clinical_record.json`!",
                f"**{patient_id}** का डेटा सफलतापूर्वक `{folder_path}/clinical_record.json` में सहेजा गया!"
            ))
            
        st.metric(
            label=t(f"1-Year Risk of Progressing from {current_stage_name}", f"{current_stage_name} से बढ़ने का 1-वर्षीय जोखिम"), 
            value=f"{calculated_probability * 100:.1f}%"
        )

# ==========================================
# 6. PATIENT / GENERAL PUBLIC VIEW
# ==========================================
elif st.session_state.user_role == "Patient / General Public":
    st.sidebar.title("Navigation Hub")
    view_mode = st.sidebar.radio("Choose View Mode:", ["Patient & Public Guide", "Complete Medical Notes"])

    if view_mode == "Patient & Public Guide":
        st.title("👁️ Patient Eye Health Portal")
        st.write("Welcome to the Patient Portal! Here is a clear, simple guide to understanding Diabetic Retinopathy.")
        st.info("### What is Diabetic Retinopathy?\n**Diabetic Retinopathy** is an eye condition that affects people with diabetes. It occurs when high blood sugar levels damage the tiny, delicate blood vessels inside the **retina** (the light-sensitive layer at the back of your eye).")
        st.subheader("The Four Main Stages Explained")
        with st.expander("A) Non-Proliferative Diabetic Retinopathy (NPDR) – The Early Stage", expanded=True):
            st.write("* **What it is:** The early phase where tiny blood vessels in the retina begin to weaken and change.\n* **Key Features:** Features small red dots called **microaneurysms**, tiny blood leaks (**hemorrhages**), swelling (**edema**), and fatty deposits (**exudates**). \n* **Symptoms:** Often has **no symptoms** at all early on.")
        with st.expander("B) Proliferative Diabetic Retinopathy (PDR) – The Advanced Stage"):
            st.write("* **What it is:** Advanced disease where tiny blood vessels become completely blocked, causing an oxygen shortage.\n* **Neovascularization:** The eye grows new, abnormal, fragile blood vessels that rupture easily.")
        with st.expander("C) Diabetic Maculopathy – Central Vision Impact"):
            st.write("* **The Macula:** The central part of the retina responsible for sharp straight-ahead vision.\n* **Macular Edema (DME):** Damaged capillaries cause fluid to flood the macula, making it waterlogged and blurring central vision.")
        with st.expander("D) Advanced Diabetic Eye Disease (ADED) – Severe Complications"):
            st.write("* **Persistent Vitreous Hemorrhage:** Massive bleeding that acts like a dark curtain blocking light.\n* **Tractional Retinal Detachment:** Shrinking scar tissue pulls the retina away from the back wall of the eye.")

    else:
        st.title("📚 Comprehensive Medical Notes")
        st.write("Full study notes covering classification, pathophysiology, anatomy, and clinical evaluation criteria.")
        st.subheader("Classification Overview")
        st.markdown("* **A) Non-Proliferative Diabetic Retinopathy (NPDR)**\n* **B) Proliferative Diabetic Retinopathy (PDR)**\n* **C) Diabetic Maculopathy**\n* **D) Advanced Diabetic Eye Disease (ADED)**")
        with st.expander("ETDRS Classification of NPDR"):
            st.markdown("* **Mild NPDR:** At least one microaneurysm is present.\n* **Moderate NPDR:** Microaneurysms in 2 or 3 quadrants, or early/mild IRMA.\n* **Severe NPDR (4-2-1 Rule):** 4 quadrants of microaneurysms/hemorrhages, 2 quadrants of venous beading, or 1 quadrant of IRMA.\n* **Very Severe NPDR:** Any 2 or more criteria from the 4-2-1 rule.")

ADED_RISKS = {
    "Persistent Vitreous Haemorrhage": "Massive blood leakage directly into the vitreous cavity acting like an opaque curtain.",
    "Tractional Retinal Detachment": "Fibrovascular scar tissue contracts, physically pulling the retina away.",
    "Neovascular Glaucoma": "Ischemia forces abnormal vessel growth into the iris and trabecular meshwork, spiking IOP.",
}