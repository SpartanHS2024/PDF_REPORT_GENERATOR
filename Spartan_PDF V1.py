import os
import sys
import logging
import requests
import time
from io import BytesIO
from pathlib import Path
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.pdfgen import canvas

# Global logger variable
logger = None

def setup_logging(output_dir):
    """Setup logging to both file and console"""
    global logger
    
    # Create logs directory if it doesn't exist
    log_dir = Path(output_dir) / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Create log filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"spartan_solar_{timestamp}.log"
    
    # Setup logging configuration
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logger = logging.getLogger(__name__)
    return logger

class AuroraAPI:
    def __init__(self, api_key, tenant_id, logger):
        self.api_key = api_key
        self.tenant_id = tenant_id
        self.base_url = "https://api.aurorasolar.com"
        self.headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        self.logger = logger

    def validate_credentials(self):
        """Test API credentials and tenant ID."""
        try:
            response = requests.get(
                f"{self.base_url}/tenants/{self.tenant_id}",
                headers=self.headers,
                timeout=30
            )
            
            if response.status_code == 401:
                self.logger.error("API authentication failed - check your API key")
                return False
            elif response.status_code == 403:
                self.logger.error("API authorization failed - check your tenant ID and permissions")
                return False
            elif response.status_code == 404:
                self.logger.error("Tenant ID not found")
                return False
                
            response.raise_for_status()
            return True
        except Exception as e:
            self.logger.error(f"Failed to validate credentials: {str(e)}")
            return False

    def _make_request(self, endpoint, method='GET', params=None):
        """Make API request with enhanced debugging."""
        url = f"{self.base_url}/tenants/{self.tenant_id}{endpoint}"
        try:
            self.logger.info(f"Making {method} request to: {url}")
            self.logger.debug(f"Request headers: {self.headers}")
            self.logger.debug(f"Request params: {params}")
            
            response = requests.request(
                method, 
                url, 
                headers=self.headers, 
                params=params, 
                timeout=30
            )
            
            self.logger.debug(f"Response status code: {response.status_code}")
            self.logger.debug(f"Response headers: {response.headers}")
            
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                self.logger.error(f"HTTP Error: {str(e)}")
                self.logger.error(f"Response body: {response.text}")
                return {}
                
            try:
                data = response.json()
                self.logger.debug(f"Response data: {data}")
                return data
            except ValueError as e:
                self.logger.error(f"Invalid JSON in response: {str(e)}")
                self.logger.error(f"Raw response: {response.text}")
                return {}
                
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request failed: {str(e)}")
            return {}

    def get_project(self, project_id):
        return self._make_request(f"/projects/{project_id}")

    def get_design_summary(self, design_id):
        return self._make_request(f"/designs/{design_id}/summary")

    def get_design_assets(self, design_id):
        return self._make_request(f"/designs/{design_id}/assets")

    def get_design_pricing(self, design_id):
        data = self._make_request(f"/designs/{design_id}/pricing")
        return data.get('pricing', {})

    def download_image(self, url):
        """Download image from URL with improved error handling and token management."""
        try:
            self.logger.info(f"Downloading image from: {url}")
            
            # Handle different URL types
            if url.startswith('https://aurora-user-data.s3.amazonaws.com'):
                # For S3 URLs, use standard headers
                headers = {'Accept': 'image/*'}
            else:
                # For other URLs, use full API headers
                headers = self.headers
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            # Verify we received image data
            content_type = response.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                self.logger.error(f"Received non-image content type: {content_type}")
                return None
            
            # Log successful download
            self.logger.info(f"Successfully downloaded image ({len(response.content)} bytes)")
            return BytesIO(response.content)
            
        except Exception as e:
            self.logger.error(f"Failed to download image: {str(e)}")
            return None

class FooterCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self.pages = []

    def showPage(self):
        self.pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_count = len(self.pages)
        for page_num, page in enumerate(self.pages, 1):
            self.__dict__.update(page)
            self.draw_footer(page_num, page_count)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_footer(self, page_num, page_count):
        width = self._pagesize[0]
        current_time = datetime.now().strftime("%B %d, %Y %I:%M %p")
        page_info = f"Page {page_num} of {page_count}"
        
        self.setFont("Helvetica", 9)
        self.drawString(72, 30, " SPARTAN HOME SERVICES " + current_time)
        page_num_width = self.stringWidth(page_info, "Helvetica", 9)
        self.drawString(width - 72 - page_num_width, 30, page_info)

class PDFGenerator:
    def __init__(self, filename, logger):
        self.filename = filename
        self.logger = logger
        self.doc = SimpleDocTemplate(
            filename,
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=36,
            bottomMargin=72
        )
        self.styles = getSampleStyleSheet()
        self.elements = []
        
        self.styles.add(ParagraphStyle(
            name='SpartanTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            textColor=colors.HexColor('#44A5DB'),
            fontName='Helvetica-Bold'
        ))
        
        self.styles.add(ParagraphStyle(
            name='ReportHeader',
            parent=self.styles['Heading2'],
            fontSize=18,
            spaceAfter=20,
            textColor=colors.black,
            fontName='Helvetica-Bold'
        ))
        
        self.styles.add(ParagraphStyle(
            name='CustomBody',
            parent=self.styles['Normal'],
            fontSize=12,
            spaceAfter=12,
            leading=14
        ))

    def add_logo(self, logo_path):
        try:
            logo = Image(logo_path)
            max_width = self.doc.width * 0.25
            aspect = logo.imageHeight / float(logo.imageWidth)
            logo.drawWidth = max_width
            logo.drawHeight = max_width * aspect
            self.elements.append(logo)
            self.elements.append(Spacer(1, 0.25*inch))
            return True
        except Exception as e:
            self.logger.error(f"Error adding logo: {e}")
            return False

    def add_title(self, text):
        self.elements.append(Paragraph(f"<b>{text}</b>", self.styles['SpartanTitle']))
        self.elements.append(Spacer(1, 0.25*inch))

    def add_header(self, text):
        self.elements.append(Paragraph(text, self.styles['ReportHeader']))
        self.elements.append(Spacer(1, 0.25*inch))

    def add_paragraph(self, text):
        self.elements.append(Paragraph(text, self.styles['CustomBody']))
        self.elements.append(Spacer(1, 0.12*inch))

    def add_table(self, data, col_widths=None, style=None):
        """Add a formatted table to the document with text wrapping."""
        if col_widths is None:
            col_widths = [2.5*inch, 3.5*inch]
            
        table = Table(data, colWidths=col_widths)
        if style is None:
            style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#44A5DB')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 14),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('WORDWRAP', (0, 0), (-1, -1), True),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('ROWHEIGHT', (0, 0), (-1, -1), 30),
            ])
        table.setStyle(style)
        self.elements.append(table)
        self.elements.append(Spacer(1, 0.25*inch))

    def add_image(self, image_data, width_percentage=0.8):
        """Add an image to the PDF with proper scaling."""
        try:
            if image_data:
                img = Image(image_data)
                
                # Calculate dimensions while maintaining aspect ratio
                max_width = self.doc.width * width_percentage
                aspect = img.imageHeight / float(img.imageWidth)
                
                # Set maximum height to 6 inches to prevent oversized images
                max_height = 6 * inch
                
                # Calculate dimensions
                img.drawWidth = max_width
                img.drawHeight = max_width * aspect
                
                # If height exceeds max, scale down proportionally
                if img.drawHeight > max_height:
                    img.drawHeight = max_height
                    img.drawWidth = max_height / aspect
                
                self.elements.append(img)
                self.elements.append(Spacer(1, 0.25*inch))
                return True
        except Exception as e:
            self.logger.error(f"Error adding image to PDF: {str(e)}")
        return False

    def generate(self):
        try:
            self.doc.build(self.elements, canvasmaker=FooterCanvas)
            return True
        except Exception as e:
            self.logger.error(f"Error generating PDF: {e}")
            return False

class AuroraSolarReport:
    def __init__(self, api_key, tenant_id, output_dir, logger, logo_path=None):
        self.api = AuroraAPI(api_key, tenant_id, logger)
        self.output_dir = output_dir
        self.logo_path = logo_path
        self.logger = logger

    def format_project_overview(self, project_data):
        if not project_data or 'project' not in project_data:
            return None
                
        project = project_data['project']
        location = project.get('location', {})
        address_components = location.get('property_address_components', {})
        
        try:
            created_dt = datetime.fromisoformat(project.get('created_at', '').replace('Z', '+00:00'))
            formatted_date = created_dt.strftime('%B %d, %Y')
        except:
            formatted_date = project.get('created_at', 'N/A')
        customer_name = f"{project.get('customer_first_name', '')} {project.get('customer_last_name', '')}".strip()
        overview_data = [
            ['Project Details', 'Information'],
            ['Project Name', project.get('name', 'N/A')],
            ['Customer Name', customer_name or 'N/A'],
            ['Street Address', address_components.get('street_address', 'N/A')],
            ['City', address_components.get('city', 'N/A')],
            ['State', address_components.get('region', 'N/A')],
            ['ZIP Code', address_components.get('postal_code', 'N/A')],
            ['Created Date', formatted_date],
            ['Status', project.get('status', 'N/A').title()],
            ['Property Type', project.get('project_type', 'N/A').title()]
        ]
        
        return overview_data

    def generate_design_report(self, design_id, project_id=None):
        """Generate a report for a specific design ID with improved image handling."""
        try:
            # Validate API credentials first
            if not self.api.validate_credentials():
                self.logger.error("Failed to validate API credentials")
                return False

            # Fetch design-specific data
            design_summary = self.api.get_design_summary(design_id)
            if not design_summary:
                self.logger.error("Failed to fetch design summary")
                return False

            design_pricing = self.api.get_design_pricing(design_id)
            design_assets = self.api.get_design_assets(design_id)
            
            # Fetch project data if project_id is provided
            # Fetch project data if project_id is provided
            project_data = None
            if project_id:
                project_data = self.api.get_project(project_id)
            
            # Create PDF generator
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"aurora_solar_report_design_{design_id}_{timestamp}.pdf"
            full_path = os.path.join(self.output_dir, filename)
            
            pdf = PDFGenerator(full_path, self.logger)
            
            # Add logo if available
            if self.logo_path and os.path.exists(self.logo_path):
                self.logger.info("Adding logo to PDF")
                pdf.add_logo(self.logo_path)
            
            # Add title and overview
            pdf.add_title("Spartan EagleEye Report")
            
            # Add project information if available
            if project_data:
                pdf.add_header("Project Overview")
                overview_data = self.format_project_overview(project_data)
                if overview_data:
                    pdf.add_table(overview_data)

            # Add system design details
            pdf.add_header("System Design Details")
            design_info = design_summary.get('design', {})
            materials = {item['component_type']: item for item in design_info.get('bill_of_materials', [])}
            modules = materials.get('modules', {})
            inverters = materials.get('microinverters', {})
            system_size = design_info.get('system_size_stc', 0) / 1000
            annual_production = design_info.get('energy_production', {}).get('annual', 0)
            arrays = design_info.get('arrays', [{}])
            solar_access = arrays[0].get('shading', {}).get('solar_access', {}).get('annual', 0)
            
            design_data = [
                ["Metric", "Value"],
                ["System Size", f"{system_size:.2f} kW"],
                ["Annual Production", f"{annual_production:,.0f} kWh"],
                ["Number of Panels", str(modules.get('quantity', 'N/A'))],
                ["Panel Model", modules.get('name', 'N/A')],
                ["Inverter Model", inverters.get('name', 'N/A')],
                ["Solar Access", f"{solar_access:.1f}%" if solar_access else "N/A"]
            ]
            pdf.add_table(design_data)
            
            # Add enhanced financial information
            if design_pricing:
                pdf.add_header("Financial Overview")
                price = design_pricing.get('system_price', 0)
                financial_data = [
                    ["Item", "Amount"],
                    ["System Price", f"${price:,.2f}"],
                    ["Price per Watt", f"${price/(system_size*1000):,.2f}/W" if system_size > 0 else "N/A"],
                    ["Federal Tax Credit", f"${price*0.30:,.2f}"],
                    ["Net System Cost", f"${price*0.70:,.2f}"]
                ]
                pdf.add_table(financial_data)
            
            # Add design images if available
            if design_assets.get('assets'):
                pdf.add_header("System Design Visualization")
                
                # Track if we successfully added any images
                images_added = False
                
                # Filter for CAD screenshots and layout images
                layout_images = [
                    asset for asset in design_assets['assets']
                    if asset.get('type') in ['layout_image'] or asset.get('asset_type') == 'CAD Screenshot'
                ]
                
                if not layout_images:
                    self.logger.warning("No layout images or CAD screenshots found in design assets")
                    pdf.add_paragraph("System design images are currently unavailable.")
                else:
                    for asset in layout_images:
                        self.logger.info(f"Processing image: {asset.get('type') or asset.get('asset_type')}")
                        
                        # Get the URL from the asset
                        image_url = asset.get('url')
                        if not image_url:
                            continue
                            
                        # Download image with retries
                        max_retries = 3
                        for attempt in range(max_retries):
                            try:
                                self.logger.info(f"Download attempt {attempt + 1} for image")
                                image_data = self.api.download_image(image_url)
                                
                                if image_data:
                                    if pdf.add_image(image_data):
                                        images_added = True
                                        self.logger.info("Successfully added image to PDF")
                                        break
                                    else:
                                        self.logger.error("Failed to add image to PDF")
                                
                                if attempt < max_retries - 1:
                                    self.logger.info("Waiting before retry...")
                                    time.sleep(2)  # Increased wait time between retries
                                    
                            except Exception as e:
                                self.logger.error(f"Error processing image: {str(e)}")
                                if attempt < max_retries - 1:
                                    continue
                                break
                    
                    if not images_added:
                        self.logger.warning("Failed to add any images to the PDF")
                        pdf.add_paragraph("System design images are currently unavailable.")
            
            # Generate the final PDF
            if pdf.generate():
                self.logger.info(f"PDF report generated successfully at: {full_path}")
                return True
            else:
                self.logger.error("Failed to generate PDF report")
                return False
                
        except Exception as e:
            self.logger.error(f"Error generating report: {str(e)}")
            return False

def main():
    # Configuration
    API_KEY = "rk_prod_75eafe223db3f63c30a0efad"
    TENANT_ID = "06a7ae68-5de3-42a6-968c-2f8fa4431a12"
    OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Documents")
    LOGO_PATH = os.path.join(os.path.expanduser("~"), "Downloads", "logo.png")
    DESIGN_ID = "f9d4fbe6-39ee-46a8-b4bb-bb7ee879453e"
    PROJECT_ID = "2af907f0-62bc-4daf-a31a-c80e686824a5"
    
    try:
        # Setup logging first
        global logger
        logger = setup_logging(OUTPUT_DIR)
        
        # Initialize report generator
        report_generator = AuroraSolarReport(API_KEY, TENANT_ID, OUTPUT_DIR, logger, LOGO_PATH)
        
        # Generate report for specific design
        success = report_generator.generate_design_report(DESIGN_ID, PROJECT_ID)
        
        if success:
            logger.info("Report generated successfully!")
            print("Report generated successfully!")
        else:
            logger.error("Failed to generate report")
            print("Failed to generate report. Check the logs for details.")
            
    except Exception as e:
        if logger:
            logger.error(f"Error in main: {str(e)}")
        print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()