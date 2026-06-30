"""Convert a technical design PNG image to a professional scaled PDF."""

import sys
from pathlib import Path
from PIL import Image
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Image as RLImage

def convert_png_to_pdf(png_path: str | Path, pdf_path: str | Path) -> None:
    png_path = Path(png_path)
    pdf_path = Path(pdf_path)
    
    if not png_path.exists():
        raise FileNotFoundError(f"Source PNG not found at {png_path}")
        
    print(f"Reading image from: {png_path}")
    with Image.open(png_path) as img:
        width, height = img.size
        
    print(f"Image dimensions: {width}x{height}")
    
    # Determine page orientation based on aspect ratio
    is_landscape = width > height
    
    if is_landscape:
        print("Landscape orientation detected.")
        page_size = landscape(letter)
        page_width, page_height = page_size
    else:
        print("Portrait orientation detected.")
        page_size = letter
        page_width, page_height = page_size
        
    # Standard margins (0.5 inch / 36 points)
    margin = 36
    usable_width = page_width - (margin * 2)
    usable_height = page_height - (margin * 2)
    
    # Calculate scale factor to fit within margins while maintaining aspect ratio
    scale_x = usable_width / width
    scale_y = usable_height / height
    scale = min(scale_x, scale_y)
    
    new_width = width * scale
    new_height = height * scale
    
    print(f"Scaled image dimensions: {new_width:.1f}x{new_height:.1f} points")
    
    # Setup document
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=page_size,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin
    )
    
    # Create the reportlab image flowable
    rl_img = RLImage(str(png_path), width=new_width, height=new_height)
    story = [rl_img]
    
    print(f"Generating PDF: {pdf_path}")
    doc.build(story)
    print("Success!")

if __name__ == "__main__":
    src_png = "/Users/anigaabhisathvikreddy/.gemini/antigravity/brain/3b97fc05-8f73-46fe-88fd-503f560e20d7/media__1782751557432.png"
    dest_pdf = "Technical_Design_Eightfold.pdf"
    
    if len(sys.argv) > 1:
        src_png = sys.argv[1]
    if len(sys.argv) > 2:
        dest_pdf = sys.argv[2]
        
    try:
        convert_png_to_pdf(src_png, dest_pdf)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
