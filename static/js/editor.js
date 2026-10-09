/**
 * Interactive Dimension Editor — Focus Mode, Sub-Pixel Vector Snapping,
 * Header Box Adjustments, Smooth Zoom & Pan, Endpoint Extent Editing, and Live Invariant Sync.
 */

import { CoordinateTransform } from './coordinates.js';
import { SnappingEngine } from './snapping.js';

export class DimensionEditor {
  constructor(containerId = 'editorContainer', docId = 'sample') {
    this.container = document.getElementById(containerId);
    this.docId = docId;
    this.transform = new CoordinateTransform(612, 792, 300);
    this.snapping = new SnappingEngine(8.0);

    this.model = null;
    this.initialAutoModel = null;
    this.history = [];
    this.historyIndex = -1;

    this.selectedIds = new Set();
    this.hoveredId = null;
    this.activeTool = 'select'; // 'select' | 'pan' | 'measure'
    this.dragState = null;
    this.measurePoints = [];

    // Focus Target & Visibility
    this.activeTarget = 'target_table'; // 'target_table' | 'target_columns' | 'target_rows' | 'target_boxes' | 'target_header' | 'target_logo' | 'target_footer' | 'target_margins' | 'target_all'
    this.showContext = true;
    this.compareGhost = false;

    // Viewport transform
    this.zoom = 1.0;
    this.panX = 0;
    this.panY = 0;
    this.isPanning = false;
    this.panStart = { x: 0, y: 0 };
    this.isFullscreen = false;
    this.isSidebarCollapsed = false;
    this.isSpacePressed = false;

    // Units
    this.displayUnit = 'pt';
    this.displayDecimals = 2;

    this.initDOM();
    this.bindEvents();
  }

  initDOM() {
    if (!this.container) return;
    this.container.innerHTML = `
      <div class="editor-workbench flex flex-col h-full w-full bg-slate-950 text-slate-100 select-none overflow-hidden rounded-2xl border border-slate-800 shadow-2xl">
        
        <!-- Top Toolbar -->
        <div class="editor-toolbar flex flex-wrap items-center justify-between px-4 py-2 bg-slate-900 border-b border-slate-800 text-xs gap-2">
          
          <!-- Focus Mode Selector & Tools -->
          <div class="flex items-center space-x-2">
            
            <!-- Focus Target Dropdown -->
            <div class="flex items-center space-x-1.5 bg-slate-950 px-2.5 py-1 rounded-lg border border-slate-800 shadow-inner">
              <span class="font-bold text-cyan-400 flex items-center space-x-1">
                <i class="fa-solid fa-crosshairs"></i> <span>Fit Target:</span>
              </span>
              <select id="focusTargetSelect" class="bg-transparent text-white font-semibold focus:outline-none cursor-pointer">
                <option value="target_table" selected>Table Grid</option>
                <option value="target_header">Header / Account Box</option>
                <option value="target_columns">Columns</option>
                <option value="target_rows">Rows</option>
                <option value="target_boxes">Boxes (Containers)</option>
                <option value="target_logo">Brand Logo</option>
                <option value="target_footer">Footer</option>
                <option value="target_margins">Margins</option>
                <option value="target_all">All Elements (Page)</option>
              </select>
            </div>

            <!-- Page Selector & Analyze Button -->
            <div class="flex items-center space-x-1.5 bg-slate-950 px-2.5 py-1 rounded-lg border border-slate-800 shadow-inner">
              <span class="font-bold text-amber-400 flex items-center space-x-1">
                <i class="fa-regular fa-file-lines"></i> <span>Page:</span>
              </span>
              <select id="editorPageSelect" class="bg-transparent text-white font-semibold focus:outline-none cursor-pointer">
                <option value="1">Page 1</option>
              </select>
              <button id="btnAnalyzeThisPage" class="px-2 py-0.5 rounded bg-blue-600 hover:bg-blue-500 text-white font-medium text-[11px] shadow-sm transition flex items-center space-x-1 ml-1" title="Analyze & Reverse-Engineer Selected Page Only">
                <i class="fa-solid fa-bolt text-yellow-300"></i> <span>Analyze Page</span>
              </button>
            </div>

            <!-- Show Context Dimmed Toggle -->
            <label class="flex items-center space-x-1 text-slate-400 hover:text-slate-200 cursor-pointer text-[11px] px-2 py-1 rounded bg-slate-800/60">
              <input type="checkbox" id="toggleShowContext" checked class="rounded bg-slate-900 border-slate-700 text-blue-500">
              <span>Show Context</span>
            </label>

            <div class="h-4 w-px bg-slate-700 mx-1"></div>

            <!-- Tool Mode Buttons -->
            <button id="btnToolSelect" class="tool-btn active px-2.5 py-1 rounded-lg bg-blue-600 text-white font-medium flex items-center space-x-1 transition" title="Select & Drag (V)">
              <i class="fa-solid fa-arrow-pointer"></i> <span>Select</span>
            </button>
            <button id="btnToolPan" class="tool-btn px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 flex items-center space-x-1 transition" title="Hand / Pan (H)">
              <i class="fa-solid fa-hand"></i> <span>Hand</span>
            </button>
            <button id="btnToolMeasure" class="tool-btn px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 flex items-center space-x-1 transition" title="Measure Distance (M)">
              <i class="fa-solid fa-ruler"></i> <span>Measure</span>
            </button>

            <!-- Guide Actions -->
            <button id="btnAddVGuide" class="px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 flex items-center space-x-1 transition" title="Add Vertical Guide">
              <i class="fa-solid fa-arrows-left-right text-cyan-400"></i> <span>+ V-Rule</span>
            </button>
            <button id="btnAddHGuide" class="px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 flex items-center space-x-1 transition" title="Add Horizontal Guide">
              <i class="fa-solid fa-arrows-up-down text-cyan-400"></i> <span>+ H-Rule</span>
            </button>
            <button id="btnDeleteSelected" class="px-2 py-1 rounded-lg bg-slate-800 hover:bg-red-900/60 text-slate-300 hover:text-red-300 flex items-center space-x-1 transition" title="Delete Selected Guide (Del)">
              <i class="fa-regular fa-trash-can"></i>
            </button>
          </div>

          <!-- Snapping, Compare & Actions -->
          <div class="flex items-center space-x-2">
            <!-- Snapping Toggle -->
            <button id="btnToggleSnap" class="px-2.5 py-1 rounded-lg bg-emerald-950/60 border border-emerald-500/40 text-emerald-300 font-medium flex items-center space-x-1 transition" title="Toggle Snapping (S)">
              <i class="fa-solid fa-magnet"></i> <span>Snap: ON</span>
            </button>

            <!-- Compare Ghost Toggle -->
            <button id="btnToggleCompare" class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 flex items-center space-x-1 transition" title="Compare against original Auto Detections">
              <i class="fa-solid fa-code-compare text-amber-400"></i> <span>Compare Ghost</span>
            </button>

            <!-- Undo / Redo -->
            <button id="btnUndo" class="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition" title="Undo (Ctrl+Z)"><i class="fa-solid fa-rotate-left"></i></button>
            <button id="btnRedo" class="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition" title="Redo (Ctrl+Y)"><i class="fa-solid fa-rotate-right"></i></button>

            <div class="h-4 w-px bg-slate-700 mx-1"></div>

            <!-- Zoom Controls -->
            <div class="flex items-center bg-slate-950 border border-slate-800 rounded-lg p-0.5 space-x-1">
              <button id="btnZoomOut" class="p-1 rounded hover:bg-slate-800 text-slate-300" title="Zoom Out (-)"><i class="fa-solid fa-minus"></i></button>
              <button id="btnZoomReset" class="font-mono text-xs px-1.5 py-0.5 rounded hover:bg-slate-800 text-slate-200 font-semibold" title="Reset (100%)"><span id="zoomLevelDisplay">100%</span></button>
              <button id="btnZoomIn" class="p-1 rounded hover:bg-slate-800 text-slate-300" title="Zoom In (+)"><i class="fa-solid fa-plus"></i></button>
            </div>
            <button id="btnZoomFitPage" class="px-2.5 py-1 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-[11px] font-bold flex items-center space-x-1 shadow-sm transition" title="Fit Entire Page (0)"><i class="fa-solid fa-expand"></i> <span>Fit Page</span></button>
            <button id="btnZoomFitWidth" class="px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] font-medium transition" title="Fit Width (W)">Width</button>
            <button id="btnZoomFitTarget" class="px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] font-medium transition" title="Fit Target (F)">Target</button>
            <button id="btnToggleSidebar" class="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition" title="Toggle Sidebar (B)"><i class="fa-solid fa-table-columns"></i></button>
            <button id="btnToggleFullscreen" class="px-2.5 py-1 rounded-lg bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-500 hover:to-blue-500 text-white font-medium flex items-center space-x-1.5 shadow-sm transition" title="Toggle Fullscreen Workbench (F11 / Esc)"><i class="fa-solid fa-up-right-and-down-left-from-center text-[10px]"></i> <span>Maximize</span></button>

            <button id="btnSaveEdits" class="px-3 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium flex items-center space-x-1 shadow-sm transition" title="Save edits to sidecar JSON">
              <i class="fa-solid fa-floppy-disk"></i> <span>Save</span>
            </button>
          </div>
        </div>

        <!-- Action Bar: Fast Alignment & Real-PDF Snapping -->
        <div class="editor-action-bar px-4 py-1.5 bg-slate-900/90 border-b border-slate-800 flex flex-wrap items-center justify-between text-xs gap-2">
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-slate-400 font-semibold">PDF Actions:</span>
            <button id="btnSnapAllColumns" class="px-2.5 py-1 rounded-md bg-indigo-950/80 hover:bg-indigo-900 border border-indigo-500/40 text-indigo-300 font-medium flex items-center space-x-1 transition shadow-sm" title="Snap all column rules to nearest painted PDF vector rules">
              <i class="fa-solid fa-wand-magic-sparkles text-cyan-400"></i> <span>Snap All Columns to Rules</span>
            </button>
            <button id="btnFitTableInk" class="px-2.5 py-1 rounded-md bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 font-medium flex items-center space-x-1 transition" title="Expand table bounds to cover suffix text (e.g. 'Cr.') and outer borders">
              <i class="fa-solid fa-arrows-left-right-to-line text-blue-400"></i> <span>Fit Table to Outer Rules + Ink</span>
            </button>
            <button id="btnDeduplicateGuides" class="px-2.5 py-1 rounded-md bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 font-medium flex items-center space-x-1 transition" title="Merge guides closer than 1.5 pt">
              <i class="fa-solid fa-code-merge text-amber-400"></i> <span>Remove Near-Duplicates</span>
            </button>
            <button id="btnCopyAIPrompt" class="px-3 py-1 rounded-md bg-gradient-to-r from-cyan-700 to-blue-700 hover:from-cyan-600 hover:to-blue-600 border border-cyan-400/50 text-white font-bold flex items-center space-x-1.5 transition shadow-md" title="Copy complete Prompt & exact dimensions to generate an identical PDF with any AI (ChatGPT, Claude, Gemini)">
              <i class="fa-solid fa-wand-magic-sparkles text-yellow-300"></i> <span>⚡ Copy AI PDF Generator Prompt</span>
            </button>
            <button id="btnCopyTemplateSpec" class="px-2.5 py-1 rounded-md bg-indigo-950/70 hover:bg-indigo-900 border border-indigo-500/40 text-cyan-300 font-medium flex items-center space-x-1 transition shadow-sm" title="Copy exact verified dimension & position template to verify other PDFs">
              <i class="fa-solid fa-stamp text-cyan-400"></i> <span>Copy Template Preset</span>
            </button>
            <button id="btnCopyFitReport" class="px-2.5 py-1 rounded-md bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 font-medium flex items-center space-x-1 transition" title="Copy Auto vs Final audit comparison report">
              <i class="fa-regular fa-clipboard text-emerald-400"></i> <span>Copy Fit Report</span>
            </button>
          </div>

          <!-- State Colors Legend -->
          <div class="flex items-center space-x-3 text-[11px]">
            <span class="flex items-center space-x-1"><span class="w-2.5 h-2.5 rounded-full bg-slate-400 inline-block"></span> <span class="text-slate-400">Auto OK</span></span>
            <span class="flex items-center space-x-1"><span class="w-2.5 h-2.5 rounded-full bg-amber-400 inline-block"></span> <span class="text-amber-400">Suspicious</span></span>
            <span class="flex items-center space-x-1"><span class="w-2.5 h-2.5 rounded-full bg-cyan-400 inline-block"></span> <span class="text-cyan-400">Manual</span></span>
            <span class="flex items-center space-x-1"><span class="w-2.5 h-2.5 rounded-full bg-emerald-400 inline-block"></span> <span class="text-emerald-400">Snapped</span></span>
          </div>
        </div>

        <!-- Main Middle Area: Center Canvas Viewport & Right Properties/Dimensions -->
        <div class="editor-main-area flex-1 flex overflow-hidden relative">

          <!-- Center Canvas Viewport -->
          <div id="viewport" class="flex-1 relative bg-slate-950 overflow-hidden cursor-default">
            
            <div id="canvasTransformContainer" class="absolute top-0 left-0 origin-top-left shadow-2xl">
              <!-- Full opacity page raster underlay -->
              <img id="pageRasterImg" src="" alt="Page Raster" class="pointer-events-none block max-w-none">
              
              <!-- SVG Layer -->
              <svg id="editorSvg" class="absolute inset-0 w-full h-full" xmlns="http://www.w3.org/2000/svg">
                <defs>
                  <marker id="dimArrow" markerWidth="6" markerHeight="4" refX="5" refY="2" orient="auto">
                    <polygon points="0 0, 6 2, 0 4" fill="#38bdf8" />
                  </marker>
                  <marker id="dimArrowStart" markerWidth="6" markerHeight="4" refX="1" refY="2" orient="auto">
                    <polygon points="6 0, 0 2, 6 4" fill="#38bdf8" />
                  </marker>
                </defs>
                <g id="grpGhost"></g>
                <g id="grpDimensionLane"></g>
                <g id="grpContainers"></g>
                <g id="grpTable"></g>
                <g id="grpColumns"></g>
                <g id="grpRows"></g>
                <g id="grpGuides"></g>
                <g id="grpEndpoints"></g>
                <g id="grpBoxHandles"></g>
                <g id="grpMeasurement"></g>
                <g id="grpRoi"></g>
                <g id="grpExteriorLabels"></g>
              </svg>
            </div>

            <!-- Floating On-Canvas Quick Zoom HUD -->
            <div class="floating-zoom-hud">
              <button id="btnFloatingZoomOut" class="p-1.5 rounded hover:bg-slate-800 text-slate-300" title="Decrease Zoom (-)"><i class="fa-solid fa-minus text-xs"></i></button>
              <button id="btnFloatingZoomReset" class="font-mono text-xs px-2.5 py-1 rounded bg-slate-800 text-cyan-300 font-bold" title="Reset (100%)"><span id="floatingZoomText">100%</span></button>
              <button id="btnFloatingZoomIn" class="p-1.5 rounded hover:bg-slate-800 text-slate-300" title="Increase Zoom (+)"><i class="fa-solid fa-plus text-xs"></i></button>
              <div class="h-3.5 w-px bg-slate-700 mx-1"></div>
              <button id="btnFloatingFitPage" class="px-2.5 py-1 rounded hover:bg-blue-600/30 text-cyan-300 text-xs font-semibold" title="Fit Entire Page (0)">Fit Page</button>
              <button id="btnFloatingFitWidth" class="px-2 py-1 rounded hover:bg-slate-800 text-slate-300 text-xs font-medium" title="Fit Width (W)">Width</button>
              <button id="btnFloatingFitTarget" class="px-2 py-1 rounded hover:bg-slate-800 text-slate-300 text-xs font-semibold" title="Fit Target (F)">Fit Target</button>
              <div class="h-3.5 w-px bg-slate-700 mx-1"></div>
              <button id="btnFloatingFullscreen" class="p-1.5 rounded hover:bg-slate-800 text-slate-300" title="Toggle Fullscreen Workbench"><i class="fa-solid fa-expand text-xs"></i></button>
            </div>

            <!-- Snap HUD Indicator Badge -->
            <div id="snapHud" class="hidden absolute top-4 left-4 px-3 py-1 rounded-full bg-emerald-500/90 text-slate-950 font-mono text-xs font-bold shadow-lg pointer-events-none flex items-center space-x-1">
              <i class="fa-solid fa-magnet"></i> <span id="snapHudText">Snapped</span>
            </div>

            <!-- Status Bar -->
            <div class="absolute bottom-0 inset-x-0 bg-slate-950/90 border-t border-slate-800 px-4 py-1 flex items-center justify-between text-[11px] text-slate-400 font-mono">
              <div class="flex items-center space-x-4">
                <span id="statusBarCursorPt">Cursor: 0.00 pt, 0.00 pt</span>
                <span id="statusBarCursorMm" class="text-slate-500">0.00 mm, 0.00 mm</span>
              </div>
              <div id="statusBarMultiSelect" class="hidden text-cyan-400 font-semibold flex items-center space-x-1">
                <i class="fa-solid fa-link"></i> <span id="statusBarMultiSelectText">Multi-Select Active</span>
              </div>
              <div id="statusBarSnapTarget" class="text-emerald-400 truncate max-w-sm font-semibold">No Snap Target</div>
            </div>
          </div>

          <!-- Right Sidebar: Tabbed Dimensions | Properties | Diagnostics -->
          <div class="editor-sidebar w-96 bg-slate-900 border-l border-slate-800 flex flex-col overflow-hidden text-xs">
            
            <div class="editor-sidebar-tabs flex border-b border-slate-800 bg-slate-950">
              <button id="tabBtnDims" class="flex-1 py-2.5 font-bold text-center border-b-2 border-blue-500 text-blue-400 bg-slate-900/60">
                <i class="fa-solid fa-list-ol mr-1"></i> Dimensions
              </button>
              <button id="tabBtnChecks" class="flex-1 py-2.5 font-semibold text-center text-slate-400 hover:text-slate-200">
                <i class="fa-solid fa-triangle-exclamation mr-1"></i> Checks (<span id="checksCountBadge">0</span>)
              </button>
              <button id="tabBtnProps" class="flex-1 py-2.5 font-semibold text-center text-slate-400 hover:text-slate-200">
                <i class="fa-solid fa-sliders mr-1"></i> Properties
              </button>
            </div>

            <!-- TAB 1: Dimensions Inventory -->
            <div id="tabPanelDims" class="flex-1 flex flex-col overflow-hidden p-3 space-y-3">
              <div class="flex items-center justify-between gap-2">
                <div class="flex items-center space-x-1">
                  <button id="btnCopyAllDims" class="px-2.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium flex items-center space-x-1 shadow-sm transition">
                    <i class="fa-regular fa-copy"></i> <span>Copy All</span>
                  </button>
                  <button id="btnOpenExportModal" class="px-2 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition" title="Choose format and preview">
                    <i class="fa-solid fa-gear"></i> <span>Formats</span>
                  </button>
                </div>
                <div class="flex items-center space-x-1">
                  <select id="unitSelect" class="bg-slate-800 border border-slate-700 text-slate-200 rounded px-1.5 py-1 text-[11px]">
                    <option value="pt" selected>pt</option>
                    <option value="mm">mm</option>
                    <option value="px">px</option>
                    <option value="in">in</option>
                  </select>
                  <select id="decimalsSelect" class="bg-slate-800 border border-slate-700 text-slate-200 rounded px-1.5 py-1 text-[11px]">
                    <option value="0">0 dec</option>
                    <option value="1">1 dec</option>
                    <option value="2" selected>2 dec</option>
                    <option value="3">3 dec</option>
                  </select>
                </div>
              </div>

              <input type="text" id="dimsSearch" placeholder="Filter dimensions..." class="w-full bg-slate-950 border border-slate-800 text-slate-200 rounded-lg px-2.5 py-1.5 text-xs focus:ring-1 focus:ring-blue-500 focus:outline-none">

              <div id="dimensionsList" class="flex-1 overflow-y-auto space-y-2 custom-scrollbar pr-1"></div>
            </div>

            <!-- TAB 2: Checks & Diagnostics Panel -->
            <div id="tabPanelChecks" class="hidden flex-1 overflow-y-auto p-3 space-y-2 custom-scrollbar">
              <div id="checksListEmpty" class="text-center py-8 text-slate-500">
                <i class="fa-solid fa-circle-check text-emerald-400 text-2xl mb-2"></i>
                <p>All consistency checks passed! No suspicious objects found.</p>
              </div>
              <div id="checksListContent" class="space-y-2"></div>
            </div>

            <!-- TAB 3: Properties Inspector -->
            <div id="tabPanelProps" class="hidden flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar">
              <div id="selectionPropsEmpty" class="text-center py-12 text-slate-500">
                <i class="fa-solid fa-arrow-pointer text-2xl mb-2"></i>
                <p>Select a guide, header box, or column to inspect and adjust coordinates.</p>
              </div>
              <div id="selectionPropsContent" class="hidden space-y-3">
                <h4 id="propTitle" class="font-bold text-sm text-white">Object Properties</h4>
                <div class="space-y-2">
                  <div>
                    <label class="block text-[11px] text-slate-400 mb-0.5">Title / Label</label>
                    <input type="text" id="propInputTitle" class="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200">
                  </div>
                  <div class="grid grid-cols-2 gap-2">
                    <div>
                      <label class="block text-[11px] text-slate-400 mb-0.5">Position / X0 (pt)</label>
                      <input type="number" step="0.01" id="propInputX0" class="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1 text-xs text-slate-200 font-mono">
                    </div>
                    <div>
                      <label class="block text-[11px] text-slate-400 mb-0.5">Position / Y0 (pt)</label>
                      <input type="number" step="0.01" id="propInputY0" class="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1 text-xs text-slate-200 font-mono">
                    </div>
                  </div>
                  <div id="propBoxDimensions" class="grid grid-cols-2 gap-2">
                    <div>
                      <label class="block text-[11px] text-slate-400 mb-0.5">Width (pt)</label>
                      <input type="number" step="0.01" id="propInputW" class="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1 text-xs text-slate-200 font-mono">
                    </div>
                    <div>
                      <label class="block text-[11px] text-slate-400 mb-0.5">Height (pt)</label>
                      <input type="number" step="0.01" id="propInputH" class="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1 text-xs text-slate-200 font-mono">
                    </div>
                  </div>
                </div>
              </div>
            </div>

          </div>
        </div>

        <!-- Export Modal -->
        <div id="exportModal" class="hidden fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div class="bg-slate-900 border border-slate-800 rounded-2xl max-w-3xl w-full p-6 space-y-4 shadow-2xl flex flex-col max-h-[85vh]">
            <div class="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 class="text-base font-bold text-white flex items-center space-x-2">
                <i class="fa-solid fa-copy text-blue-400"></i>
                <span>Copy & Export Dimensions</span>
              </h3>
              <button id="btnCloseExportModal" class="text-slate-400 hover:text-white"><i class="fa-solid fa-xmark text-lg"></i></button>
            </div>

            <div class="grid grid-cols-2 sm:grid-cols-5 gap-3 text-xs">
              <div>
                <label class="block text-slate-400 mb-1 font-medium">Format</label>
                <select id="exportFormatSelect" class="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-slate-200 font-semibold">
                  <option value="ai_prompt" selected>⚡ AI Prompt & Generator Code</option>
                  <option value="markdown">Markdown Table</option>
                  <option value="prompt">Prompt-Ready Block</option>
                  <option value="tsv">TSV (Excel / Sheets)</option>
                  <option value="csv">CSV</option>
                  <option value="json">Full JSON Spec</option>
                  <option value="plain">Plain Text</option>
                </select>
              </div>
              <div>
                <label class="block text-slate-400 mb-1 font-medium">Privacy Protection</label>
                <select id="exportPrivacySelect" class="w-full bg-slate-950 border border-indigo-500/50 rounded-lg px-2.5 py-1.5 text-cyan-300 font-semibold">
                  <option value="synthetic" selected>🛡️ Synthetic Data (Safe)</option>
                  <option value="redacted">🔒 Redacted (XXXX)</option>
                  <option value="real">⚠️ Real Data (PII)</option>
                </select>
              </div>
              <div>
                <label class="block text-slate-400 mb-1 font-medium">Unit</label>
                <select id="exportUnitSelect" class="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-slate-200">
                  <option value="pt" selected>Points (pt)</option>
                  <option value="mm">Millimetres (mm)</option>
                  <option value="px">Pixels (300 DPI)</option>
                  <option value="in">Inches (in)</option>
                  <option value="all">All Units Combined</option>
                </select>
              </div>
              <div>
                <label class="block text-slate-400 mb-1 font-medium">Decimals</label>
                <select id="exportDecimalsSelect" class="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-slate-200">
                  <option value="2" selected>2 Decimals</option>
                  <option value="0">0 (Integer)</option>
                  <option value="1">1 Decimal</option>
                  <option value="3">3 Decimals</option>
                </select>
              </div>
              <div>
                <label class="block text-slate-400 mb-1 font-medium">Options</label>
                <div class="space-y-1">
                  <label class="flex items-center space-x-1.5 text-slate-300 text-[11px]">
                    <input type="checkbox" id="exportIncludeDefs" checked class="rounded bg-slate-800 border-slate-700 text-blue-500">
                    <span>Include Definitions</span>
                  </label>
                </div>
              </div>
            </div>

            <!-- Privacy Warning Banner -->
            <div id="exportPrivacyWarning" class="hidden px-3 py-2 bg-amber-950/80 border border-amber-500/60 rounded-lg text-amber-200 text-xs flex items-center space-x-2">
              <i class="fa-solid fa-triangle-exclamation text-amber-400 text-sm"></i>
              <span><strong>CAUTION:</strong> Real customer data contains sensitive names, account numbers, and transactions. Sending this to an external model (ChatGPT/Claude/Gemini) may expose PII.</span>
            </div>


            <div class="flex-1 overflow-hidden relative border border-slate-800 rounded-xl bg-slate-950 flex flex-col">
              <textarea id="exportPreviewText" readonly class="flex-1 w-full bg-transparent p-3 font-mono text-xs text-slate-200 resize-none focus:outline-none custom-scrollbar whitespace-pre"></textarea>
            </div>

            <div class="flex items-center justify-between pt-2">
              <span id="copyToast" class="text-xs text-emerald-400 font-semibold opacity-0 transition-opacity"></span>
              <div class="flex items-center space-x-2">
                <button id="btnDownloadExportFile" class="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium text-xs flex items-center space-x-1.5 transition">
                  <i class="fa-solid fa-download"></i> <span>Download File</span>
                </button>
                <button id="btnConfirmCopy" class="px-5 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-medium text-xs flex items-center space-x-1.5 shadow-lg shadow-blue-500/20 transition">
                  <i class="fa-regular fa-copy"></i> <span>Copy to Clipboard</span>
                </button>
              </div>
            </div>
          </div>
        </div>

      </div>
    `;
  }

  loadModel(editorModel, rasterUrl = null, docId = null) {
    if (docId) this.docId = docId;
    this.model = JSON.parse(JSON.stringify(editorModel));
    this.initialAutoModel = JSON.parse(JSON.stringify(editorModel));
    this.history = [JSON.parse(JSON.stringify(editorModel))];
    this.historyIndex = 0;

    this.transform = new CoordinateTransform(
      this.model.width_pt,
      this.model.height_pt,
      this.model.dpi || 300
    );

    const container = document.getElementById('canvasTransformContainer');
    if (container) {
      container.style.width = `${this.model.width_pt}px`;
      container.style.height = `${this.model.height_pt}px`;
    }

    const img = document.getElementById('pageRasterImg');
    if (img && rasterUrl) {
      if (rasterUrl.includes('annotated_page_')) {
        rasterUrl = rasterUrl.replace('annotated_page_', 'page_');
      }
      img.src = rasterUrl;
      img.style.width = '100%';
      img.style.height = '100%';
    }

    const svg = document.getElementById('editorSvg');
    if (svg) {
      svg.setAttribute('viewBox', `0 0 ${this.model.width_pt} ${this.model.height_pt}`);
      svg.style.width = '100%';
      svg.style.height = '100%';
    }

    // Update page selector dropdown
    const pageSelect = document.getElementById('editorPageSelect');
    if (pageSelect) {
      pageSelect.innerHTML = '';
      const totalPages = this.model.total_pages || 1;
      const currentPage = this.model.page_number || 1;
      for (let p = 1; p <= totalPages; p++) {
        const opt = document.createElement('option');
        opt.value = p;
        opt.textContent = `Page ${p} of ${totalPages}`;
        if (p === currentPage) opt.selected = true;
        pageSelect.appendChild(opt);
      }
    }

    // Auto-fit entire page so document is immediately visible, large, and centered
    setTimeout(() => {
      this.zoomFitPage();
    }, 60);

    this.render();
    this.renderDimensionsList();
    this.renderChecksList();
  }

  assertUniqueLayerRenderer(layerId, fnName) {
    if (!this._layerRenderMap) {
      this._layerRenderMap = new Map();
    }
    const existing = this._layerRenderMap.get(layerId);
    if (existing && existing !== fnName) {
      throw new Error(`Layer conflict: Layer '${layerId}' is claimed by both '${existing}' and '${fnName}'. Exactly one renderer allowed.`);
    }
    this._layerRenderMap.set(layerId, fnName);
  }

  render() {
    if (!this.model) return;
    this.assertUniqueLayerRenderer('grpGuides', 'renderGuides');
    this.renderGuides();

    this.assertUniqueLayerRenderer('grpBoxes', 'renderBoxes');
    this.renderBoxes();

    this.assertUniqueLayerRenderer('grpTable', 'renderTable');
    this.renderTable();

    this.assertUniqueLayerRenderer('grpColumns', 'renderColumns');
    this.renderColumns();

    this.assertUniqueLayerRenderer('grpRows', 'renderRows');
    this.renderRows();

    this.assertUniqueLayerRenderer('grpDimensionLane', 'renderDimensionLane');
    this.renderDimensionLane();

    this.assertUniqueLayerRenderer('grpEndpoints', 'renderEndpoints');
    this.renderEndpoints();

    this.assertUniqueLayerRenderer('grpHandles', 'renderBoxHandles');
    this.renderBoxHandles();

    this.assertUniqueLayerRenderer('grpGhost', 'renderGhost');
    this.renderGhost();

    this.assertUniqueLayerRenderer('grpExteriorLabels', 'renderExteriorLabels');
    this.renderExteriorLabels();
  }

  getLinkedIds(id) {
    if (!id) return [];
    const set = new Set([id]);
    if (id.startsWith('dim_col_')) {
      const colNum = id.replace('dim_col_', '').replace('_width', '');
      set.add(`col_${colNum}`);
      set.add(`col_${colNum}_rect`);
    } else if (id.startsWith('col_')) {
      const colNum = id.replace('col_', '').replace('_rect', '');
      set.add(`dim_col_${colNum}_width`);
      set.add(`col_${colNum}`);
    } else if (id.startsWith('dim_table_') || id === 'target_table' || id === 'table' || id === 'table_grid') {
      set.add('target_table');
      set.add('table');
      set.add('table_grid');
      set.add('dim_table_width');
      set.add('dim_table_height');
      set.add('dim_table_top_margin');
      set.add('dim_table_left_margin');
      set.add('dim_table_bottom_margin');
    } else if (id.startsWith('dim_row_') || id.startsWith('row_')) {
      const rowNum = id.replace('dim_row_', '').replace('row_', '').replace('_pitch', '');
      set.add(`row_${rowNum}`);
      set.add(`dim_row_${rowNum}_pitch`);
      set.add('dim_row_pitch');
      set.add('dim_body_row_pitch');
    } else if (id.startsWith('box_')) {
      set.add(id);
      set.add(`dim_${id}_width`);
      set.add(`dim_${id}_height`);
    } else if (id.startsWith('guide_')) {
      set.add(id);
    }
    return Array.from(set);
  }

  isItemActive(id) {
    if (!id) return { isSelected: false, isHovered: false };
    const linked = this.getLinkedIds(id);
    const isSelected = linked.some(it => this.selectedIds.has(it));
    const isHovered = this.hoveredId ? (linked.includes(this.hoveredId) || this.getLinkedIds(this.hoveredId).includes(id)) : false;
    return { isSelected, isHovered };
  }

  setHovered(id) {
    if (this.hoveredId === id) return;
    this.hoveredId = id;
    this.updateHighlightStyles();
  }

  setSelected(id, multi = false) {
    if (!multi) {
      this.selectedIds.clear();
    }
    if (id) {
      if (this.selectedIds.has(id)) {
        if (multi) this.selectedIds.delete(id);
      } else {
        this.selectedIds.add(id);
      }
    }
    this.render();
    this.renderDimensionsList();
    this.showPropertiesPanel();
    this.scrollLinkedSidebarItemIntoView(id);
  }

  updateHighlightStyles() {
    const svg = document.getElementById('editorSvg');
    if (svg) {
      const allInteractive = svg.querySelectorAll('[data-id], .table-boundary-rect, .table-drag-bar, .column-rect, .row-separator-line, .row-band, .guide-line, .box-element');
      allInteractive.forEach(el => {
        const elId = el.dataset.id || el.dataset.boxId || el.dataset.guideId;
        const { isSelected, isHovered } = this.isItemActive(elId);
        el.classList.toggle('hovered', isHovered);
        el.classList.toggle('selected', isSelected);
      });
    }

    document.querySelectorAll('.dim-row').forEach(row => {
      const dimId = row.dataset.dimId;
      const { isSelected, isHovered } = this.isItemActive(dimId);
      row.classList.toggle('dim-row-hovered', isHovered);
      row.classList.toggle('dim-row-selected', isSelected);
    });
  }

  scrollLinkedSidebarItemIntoView(id) {
    if (!id) return;
    const list = document.getElementById('dimensionsList');
    if (!list) return;
    const linked = this.getLinkedIds(id);
    for (const lid of linked) {
      const el = list.querySelector(`.dim-row[data-dim-id="${lid}"]`);
      if (el) {
        const listRect = list.getBoundingClientRect();
        const elRect = el.getBoundingClientRect();
        if (elRect.top < listRect.top) {
          list.scrollTop += (elRect.top - listRect.top) - 8;
        } else if (elRect.bottom > listRect.bottom) {
          list.scrollTop += (elRect.bottom - listRect.bottom) + 8;
        }
        break;
      }
    }
  }

  isObjectInFocus(ownerId) {
    if (this.activeTarget === 'target_all') return true;
    if (this.activeTarget === 'target_table') {
      return ownerId === 'target_table' || ownerId === 'target_columns' || ownerId === 'target_rows';
    }
    if (this.activeTarget === 'target_header') {
      return ownerId === 'target_header' || ownerId === 'target_boxes';
    }
    return ownerId === this.activeTarget;
  }

  renderGuides() {
    const grp = document.getElementById('grpGuides');
    if (!grp) return;
    grp.innerHTML = '';

    for (const g of (this.model.guides || [])) {
      const inFocus = this.isObjectInFocus(g.owner_id);
      if (!inFocus && !this.showContext) continue;

      const { isSelected, isHovered } = this.isItemActive(g.id);
      const stateCol = isSelected ? '#38bdf8' : (isHovered ? '#00f0ff' : (
        g.state === 'green' ? '#10b981' : (g.state === 'amber' ? '#f59e0b' : (g.state === 'blue' ? '#38bdf8' : '#94a3b8'))
      ));
      const opacity = inFocus ? 1.0 : 0.2;

      const gElem = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      gElem.setAttribute('opacity', opacity);

      if (g.orientation === 'V') {
        const y0 = g.start_pt != null ? g.start_pt : 0;
        const y1 = g.end_pt != null ? g.end_pt : this.model.height_pt;

        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', g.position_pt);
        line.setAttribute('y1', y0);
        line.setAttribute('x2', g.position_pt);
        line.setAttribute('y2', y1);
        line.setAttribute('stroke', stateCol);
        line.setAttribute('stroke-width', isSelected || isHovered ? '2' : '1');
        line.setAttribute('class', `guide-line ${isSelected ? 'selected' : ''} ${isHovered ? 'hovered' : ''}`);
        line.dataset.id = g.id;

        const hit = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        hit.setAttribute('x1', g.position_pt);
        hit.setAttribute('y1', y0);
        hit.setAttribute('x2', g.position_pt);
        hit.setAttribute('y2', y1);
        hit.setAttribute('stroke', 'transparent');
        hit.setAttribute('stroke-width', '10');
        hit.setAttribute('class', 'guide-hit-area');
        hit.dataset.id = g.id;

        gElem.appendChild(line);
        gElem.appendChild(hit);
      } else {
        const x0 = g.start_pt != null ? g.start_pt : 0;
        const x1 = g.end_pt != null ? g.end_pt : this.model.width_pt;

        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', x0);
        line.setAttribute('y1', g.position_pt);
        line.setAttribute('x2', x1);
        line.setAttribute('y2', g.position_pt);
        line.setAttribute('stroke', stateCol);
        line.setAttribute('stroke-width', isSelected || isHovered ? '2' : '1');
        line.setAttribute('class', `guide-line ${isSelected ? 'selected' : ''} ${isHovered ? 'hovered' : ''}`);
        line.dataset.id = g.id;

        const hit = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        hit.setAttribute('x1', x0);
        hit.setAttribute('y1', g.position_pt);
        hit.setAttribute('x2', x1);
        hit.setAttribute('y2', g.position_pt);
        hit.setAttribute('stroke', 'transparent');
        hit.setAttribute('stroke-width', '10');
        hit.setAttribute('class', 'guide-hit-area horizontal');
        hit.dataset.id = g.id;

        gElem.appendChild(line);
        gElem.appendChild(hit);
      }
      grp.appendChild(gElem);
    }
  }

  renderEndpoints() {
    const grp = document.getElementById('grpEndpoints');
    if (!grp) return;
    grp.innerHTML = '';

    if (!this.selectedIds || this.selectedIds.size === 0) return;

    const handleSize = 6 / Math.max(0.2, this.zoom);

    for (const id of this.selectedIds) {
      const g = (this.model.guides || []).find(it => it.id === id);
      if (g && !g.locked) {
        if (g.orientation === 'V') {
          const y0 = g.start_pt != null ? g.start_pt : 0;
          const y1 = g.end_pt != null ? g.end_pt : this.model.height_pt;
          this.createHandle(grp, g.position_pt, y0, handleSize, g.id, 'start_v');
          this.createHandle(grp, g.position_pt, y1, handleSize, g.id, 'end_v');
        } else {
          const x0 = g.start_pt != null ? g.start_pt : 0;
          const x1 = g.end_pt != null ? g.end_pt : this.model.width_pt;
          this.createHandle(grp, x0, g.position_pt, handleSize, g.id, 'start_h');
          this.createHandle(grp, x1, g.position_pt, handleSize, g.id, 'end_h');
        }
      }
    }
  }

  createHandle(parent, x, y, size, guideId, handleType) {
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', x - size/2);
    rect.setAttribute('y', y - size/2);
    rect.setAttribute('width', size);
    rect.setAttribute('height', size);
    rect.setAttribute('fill', '#ffffff');
    rect.setAttribute('stroke', '#0284c7');
    rect.setAttribute('stroke-width', '1');
    rect.setAttribute('class', 'endpoint-handle');
    rect.dataset.guideId = guideId;
    rect.dataset.handleType = handleType;
    parent.appendChild(rect);
  }

  renderBoxes() {
    const grp = document.getElementById('grpContainers');
    if (!grp) return;
    grp.innerHTML = '';

    for (const b of (this.model.boxes || [])) {
      const inFocus = this.isObjectInFocus(b.owner_id);
      if (!inFocus && !this.showContext) continue;

      const { isSelected, isHovered } = this.isItemActive(b.id);
      const isHeader = b.type === 'header' || b.type === 'header_block';
      const isLogo = b.type === 'logo';

      const strokeCol = isSelected ? '#00f0ff' : (isHovered ? '#38bdf8' : (isHeader ? '#6366f1' : (isLogo ? '#0ea5e9' : '#8b5cf6')));
      const fillCol = isSelected ? 'rgba(56, 189, 248, 0.20)' : (isHovered ? 'rgba(56, 189, 248, 0.12)' : (isHeader ? 'rgba(99, 102, 241, 0.04)' : (isLogo ? 'rgba(14, 165, 233, 0.08)' : 'rgba(139, 92, 246, 0.04)')));
      const strokeDash = isSelected || isHovered ? 'none' : '4,4';

      const gBox = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      gBox.setAttribute('opacity', inFocus ? 1.0 : 0.25);

      const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      rect.setAttribute('x', b.x0_pt);
      rect.setAttribute('y', b.y0_pt);
      rect.setAttribute('width', Math.max(1.0, b.x1_pt - b.x0_pt));
      rect.setAttribute('height', Math.max(1.0, b.y1_pt - b.y0_pt));
      rect.setAttribute('fill', fillCol);
      rect.setAttribute('stroke', strokeCol);
      rect.setAttribute('stroke-width', isSelected || isHovered ? 2.0 : 1.0);
      rect.setAttribute('stroke-dasharray', strokeDash);
      rect.setAttribute('class', `box-element ${isSelected ? 'selected' : ''} ${isHovered ? 'hovered' : ''}`);
      rect.dataset.id = b.id;

      gBox.appendChild(rect);
      grp.appendChild(gBox);
    }
  }

  renderTable() {
    const grp = document.getElementById('grpTable');
    if (!grp) return;
    grp.innerHTML = '';
    if (!this.model || !this.model.table_bbox) return;
    if (!this.isObjectInFocus('target_table') && !this.isObjectInFocus('target_all')) return;

    const tBbox = this.model.table_bbox;
    const { isSelected, isHovered } = this.isItemActive('target_table');

    const gTable = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    gTable.setAttribute('id', 'table_grid_group');

    // Main Table Boundary Box
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', tBbox.x0_pt);
    rect.setAttribute('y', tBbox.y0_pt);
    rect.setAttribute('width', Math.max(1.0, tBbox.width_pt || (tBbox.x1_pt - tBbox.x0_pt)));
    rect.setAttribute('height', Math.max(1.0, tBbox.height_pt || (tBbox.y1_pt - tBbox.y0_pt)));
    rect.setAttribute('class', `table-boundary-rect ${isSelected ? 'selected' : ''} ${isHovered ? 'hovered' : ''}`);
    rect.dataset.id = 'target_table';

    // Top Header Drag Bar / Handle Tab
    const barH = 14;
    const barW = Math.min(110, (tBbox.width_pt || 110));
    const dragBar = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    dragBar.setAttribute('x', tBbox.x0_pt);
    dragBar.setAttribute('y', Math.max(0, tBbox.y0_pt - barH));
    dragBar.setAttribute('width', barW);
    dragBar.setAttribute('height', barH);
    dragBar.setAttribute('rx', 3);
    dragBar.setAttribute('fill', isSelected ? '#0284c7' : '#0f172a');
    dragBar.setAttribute('stroke', '#38bdf8');
    dragBar.setAttribute('stroke-width', '1');
    dragBar.setAttribute('class', `table-drag-bar ${isSelected ? 'selected' : ''} ${isHovered ? 'hovered' : ''}`);
    dragBar.dataset.id = 'target_table';

    const barTxt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    barTxt.setAttribute('x', tBbox.x0_pt + 6);
    barTxt.setAttribute('y', Math.max(0, tBbox.y0_pt - barH) + 10);
    barTxt.setAttribute('fill', '#ffffff');
    barTxt.setAttribute('font-size', '9');
    barTxt.setAttribute('font-family', 'sans-serif');
    barTxt.setAttribute('font-weight', 'bold');
    barTxt.setAttribute('pointer-events', 'none');
    barTxt.textContent = ':: Table Grid';

    gTable.appendChild(rect);
    gTable.appendChild(dragBar);
    gTable.appendChild(barTxt);
    grp.appendChild(gTable);
  }

  renderBoxHandles() {
    const grp = document.getElementById('grpBoxHandles');
    if (!grp) return;
    grp.innerHTML = '';

    const handleSize = 7 / Math.max(0.2, this.zoom);

    for (const id of this.selectedIds) {
      const b = (this.model.boxes || []).find(it => it.id === id);
      if (b) {
        const x0 = b.x0_pt;
        const y0 = b.y0_pt;
        const x1 = b.x1_pt;
        const y1 = b.y1_pt;
        const xm = (x0 + x1) / 2;
        const ym = (y0 + y1) / 2;

        const handles = [
          { x: x0, y: y0, type: 'nw' },
          { x: xm, y: y0, type: 'n' },
          { x: x1, y: y0, type: 'ne' },
          { x: x1, y: ym, type: 'e' },
          { x: x1, y: y1, type: 'se' },
          { x: xm, y: y1, type: 's' },
          { x: x0, y: y1, type: 'sw' },
          { x: x0, y: ym, type: 'w' },
        ];

        for (const h of handles) {
          const r = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
          r.setAttribute('x', h.x - handleSize/2);
          r.setAttribute('y', h.y - handleSize/2);
          r.setAttribute('width', handleSize);
          r.setAttribute('height', handleSize);
          r.setAttribute('class', `box-resize-handle handle-${h.type}`);
          r.dataset.boxId = b.id;
          r.dataset.handleType = h.type;
          grp.appendChild(r);
        }
      }
    }
  }

  renderColumns() {
    const grp = document.getElementById('grpColumns');
    if (!grp) return;
    grp.innerHTML = '';
    if (!this.isObjectInFocus('target_columns') && !this.isObjectInFocus('target_table') && !this.isObjectInFocus('target_all')) return;

    const tBbox = this.model.table_bbox;
    if (!tBbox) return;

    for (const col of (this.model.columns || [])) {
      const colId = `col_${col.column_index}`;
      const { isSelected, isHovered } = this.isItemActive(colId);

      const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      rect.setAttribute('x', col.x0_pt);
      rect.setAttribute('y', tBbox.y0_pt);
      rect.setAttribute('width', Math.max(0.1, col.width_pt));
      rect.setAttribute('height', Math.max(0.1, tBbox.height_pt));
      rect.setAttribute('fill', isSelected ? 'rgba(56, 189, 248, 0.18)' : (isHovered ? 'rgba(14, 165, 233, 0.12)' : 'transparent'));
      rect.setAttribute('stroke', isSelected ? '#00f0ff' : (isHovered ? '#38bdf8' : 'rgba(14, 165, 233, 0.2)'));
      rect.setAttribute('stroke-width', isSelected || isHovered ? 1.5 : 0.5);
      rect.setAttribute('class', `column-rect ${isSelected ? 'selected' : ''} ${isHovered ? 'hovered' : ''}`);
      rect.dataset.id = colId;
      grp.appendChild(rect);
    }
  }

  renderRows() {
    const grp = document.getElementById('grpRows');
    if (!grp) return;
    grp.innerHTML = '';
    if (!this.isObjectInFocus('target_rows') && !this.isObjectInFocus('target_table') && !this.isObjectInFocus('target_all')) return;

    const tBbox = this.model.table_bbox;
    if (!tBbox) return;

    const isRowsFocus = this.isObjectInFocus('target_rows');

    (this.model.rows || []).forEach((r, idx) => {
      const rowId = `row_${idx}`;
      const { isSelected, isHovered } = this.isItemActive(rowId);

      // Zebra row band
      if (r.y1_pt > r.y0_pt) {
        const band = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        band.setAttribute('x', tBbox.x0_pt);
        band.setAttribute('y', r.y0_pt);
        band.setAttribute('width', tBbox.x1_pt - tBbox.x0_pt);
        band.setAttribute('height', r.y1_pt - r.y0_pt);
        band.setAttribute('fill', isSelected ? 'rgba(56, 189, 248, 0.2)' : (isHovered ? 'rgba(56, 189, 248, 0.12)' : (idx % 2 === 0 ? 'rgba(56, 189, 248, 0.04)' : 'rgba(255, 255, 255, 0.01)')));
        band.setAttribute('class', `row-band ${isSelected ? 'selected' : ''} ${isHovered ? 'hovered' : ''}`);
        band.dataset.id = rowId;
        band.dataset.rowIndex = idx;
        grp.appendChild(band);
      }

      // Row separator line
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', tBbox.x0_pt);
      line.setAttribute('y1', r.y0_pt);
      line.setAttribute('x2', tBbox.x1_pt);
      line.setAttribute('y2', r.y0_pt);
      line.setAttribute('stroke', isSelected || isHovered ? '#38bdf8' : (isRowsFocus ? 'rgba(56, 189, 248, 0.5)' : 'rgba(148, 163, 184, 0.4)'));
      line.setAttribute('stroke-width', isSelected || isHovered ? 1.5 : (isRowsFocus ? 0.8 : 0.5));
      line.setAttribute('stroke-dasharray', isSelected || isHovered ? 'none' : '2,2');
      line.setAttribute('class', `row-separator-line ${isSelected ? 'selected' : ''} ${isHovered ? 'hovered' : ''}`);
      line.dataset.id = rowId;
      line.dataset.rowIndex = idx;
      grp.appendChild(line);

      // Hit line for resizing/moving row
      const hit = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      hit.setAttribute('x1', tBbox.x0_pt);
      hit.setAttribute('y1', r.y0_pt);
      hit.setAttribute('x2', tBbox.x1_pt);
      hit.setAttribute('y2', r.y0_pt);
      hit.setAttribute('class', 'row-hit-line');
      hit.dataset.id = rowId;
      hit.dataset.rowIndex = idx;
      grp.appendChild(hit);

      // Pitch label when in rows focus or hovered/selected
      if ((isRowsFocus || isSelected || isHovered) && r.pitch_pt > 0) {
        const pitchText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        pitchText.setAttribute('x', tBbox.x1_pt + 6);
        pitchText.setAttribute('y', (r.y0_pt + r.y1_pt) / 2 + 3);
        pitchText.setAttribute('fill', isSelected || isHovered ? '#38bdf8' : '#94a3b8');
        pitchText.setAttribute('font-size', '9');
        pitchText.setAttribute('font-family', 'ui-monospace, monospace');
        pitchText.setAttribute('font-weight', isSelected || isHovered ? 'bold' : 'normal');
        pitchText.textContent = `${r.pitch_pt.toFixed(2)} pt`;
        grp.appendChild(pitchText);
      }
    });
  }

  renderDimensionLane() {
    const grp = document.getElementById('grpDimensionLane');
    if (!grp) return;
    grp.innerHTML = '';
    if (!this.isObjectInFocus('target_table') && !this.isObjectInFocus('target_columns')) return;

    const lane = this.model.dimension_lane;
    if (!lane || !lane.arrows || lane.arrows.length === 0 || !lane.lane_y_pt || lane.lane_y_pt <= 0) return;

    const laneY = lane.lane_y_pt;

    // Extension Lines
    for (const ext of (lane.extension_lines || [])) {
      const el = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      el.setAttribute('x1', ext.x_pt);
      el.setAttribute('y1', Math.min(ext.y0_pt, laneY - 4));
      el.setAttribute('x2', ext.x_pt);
      el.setAttribute('y2', ext.y1_pt);
      el.setAttribute('stroke', ext.is_outer ? '#0ea5e9' : '#64748b');
      el.setAttribute('stroke-width', ext.is_outer ? '1.2' : '0.8');
      el.setAttribute('stroke-dasharray', ext.is_outer ? 'none' : '2,2');
      grp.appendChild(el);
    }

    // Numbered Markers (Docked Strip mode)
    const markers = lane.numbered_markers || [];
    markers.forEach((m) => {
      const gMarker = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      const pill = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      const markerY = Math.max(8, m.y_pt - 8);
      pill.setAttribute('cx', m.x_pt);
      pill.setAttribute('cy', markerY);
      pill.setAttribute('r', '7');
      pill.setAttribute('fill', '#0284c7');
      pill.setAttribute('stroke', '#38bdf8');
      pill.setAttribute('stroke-width', '1');

      const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      txt.setAttribute('x', m.x_pt);
      txt.setAttribute('y', markerY + 3.5);
      txt.setAttribute('fill', '#ffffff');
      txt.setAttribute('font-size', '8');
      txt.setAttribute('font-family', 'sans-serif');
      txt.setAttribute('font-weight', 'bold');
      txt.setAttribute('text-anchor', 'middle');
      txt.textContent = m.marker_label;

      gMarker.appendChild(pill);
      gMarker.appendChild(txt);
      grp.appendChild(gMarker);
    });

    // Arrows and Dimension Badges
    const arrows = lane.arrows || [];
    arrows.forEach((arrow, idx) => {
      const midX = (arrow.x0_pt + arrow.x1_pt) / 2.0;
      const width = arrow.width_pt;
      const labelText = arrow.label_text || `${width.toFixed(1)} pt`;

      // Main Arrow Line
      const aLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      aLine.setAttribute('x1', arrow.x0_pt + 1);
      aLine.setAttribute('y1', laneY);
      aLine.setAttribute('x2', arrow.x1_pt - 1);
      aLine.setAttribute('y2', laneY);
      aLine.setAttribute('stroke', '#38bdf8');
      aLine.setAttribute('stroke-width', '1.2');
      aLine.setAttribute('marker-start', 'url(#dimArrowStart)');
      aLine.setAttribute('marker-end', 'url(#dimArrow)');
      grp.appendChild(aLine);

      // Stagger vertical offset for narrow columns to prevent label collisions
      const isNarrow = width < 48.0;
      const yOffset = isNarrow ? (idx % 2 === 0 ? -13 : 13) : -2;

      // Label background pill
      const pillW = Math.max(38, labelText.length * 6 + 10);
      const pillH = 14;
      const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      rect.setAttribute('x', midX - pillW / 2);
      rect.setAttribute('y', laneY + yOffset - pillH / 2);
      rect.setAttribute('width', pillW);
      rect.setAttribute('height', pillH);
      rect.setAttribute('rx', 3);
      rect.setAttribute('fill', '#020617');
      rect.setAttribute('stroke', '#0ea5e9');
      rect.setAttribute('stroke-width', '0.75');

      const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      txt.setAttribute('x', midX);
      txt.setAttribute('y', laneY + yOffset + 3.5);
      txt.setAttribute('fill', '#38bdf8');
      txt.setAttribute('font-size', '9');
      txt.setAttribute('font-family', 'JetBrains Mono, monospace');
      txt.setAttribute('font-weight', '600');
      txt.setAttribute('text-anchor', 'middle');
      txt.textContent = labelText;

      grp.appendChild(rect);
      grp.appendChild(txt);
    });
  }

  renderGhost() {
    const grp = document.getElementById('grpGhost');
    if (!grp) return;
    grp.innerHTML = '';
    if (!this.compareGhost || !this.initialAutoModel) return;

    for (const g of (this.initialAutoModel.guides || [])) {
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      if (g.orientation === 'V') {
        line.setAttribute('x1', g.position_pt);
        line.setAttribute('y1', g.start_pt != null ? g.start_pt : 0);
        line.setAttribute('x2', g.position_pt);
        line.setAttribute('y2', g.end_pt != null ? g.end_pt : this.model.height_pt);
      } else {
        line.setAttribute('x1', g.start_pt != null ? g.start_pt : 0);
        line.setAttribute('y1', g.position_pt);
        line.setAttribute('x2', g.end_pt != null ? g.end_pt : this.model.width_pt);
        line.setAttribute('y2', g.position_pt);
      }
      line.setAttribute('stroke', '#f59e0b');
      line.setAttribute('stroke-width', '1');
      line.setAttribute('stroke-dasharray', '3,3');
      line.setAttribute('opacity', '0.6');
      grp.appendChild(line);
    }
  }

  renderExteriorLabels() {
    const grp = document.getElementById('grpExteriorLabels');
    if (!grp) return;
    grp.innerHTML = '';

    const labels = this.model.labels || [];
    labels.forEach(lbl => {
      const bx0 = lbl.bbox_pt[0];
      const by0 = lbl.bbox_pt[1];
      const bx1 = lbl.bbox_pt[2];
      const by1 = lbl.bbox_pt[3];
      const w = bx1 - bx0;
      const h = by1 - by0;

      const gLbl = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      gLbl.setAttribute('class', 'placed-label-group');

      if (lbl.leader_line) {
        const [lx0, ly0, lx1, ly1] = lbl.leader_line;
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', lx0);
        line.setAttribute('y1', ly0);
        line.setAttribute('x2', lx1);
        line.setAttribute('y2', ly1);
        line.setAttribute('stroke', '#64748b');
        line.setAttribute('stroke-width', '0.8');
        line.setAttribute('stroke-dasharray', '2,2');
        gLbl.appendChild(line);
      }

      const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      rect.setAttribute('x', bx0);
      rect.setAttribute('y', by0);
      rect.setAttribute('width', Math.max(10, w));
      rect.setAttribute('height', Math.max(10, h));
      rect.setAttribute('rx', 3);
      rect.setAttribute('fill', '#090d16');
      rect.setAttribute('stroke', '#38bdf8');
      rect.setAttribute('stroke-width', '0.75');

      const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      txt.setAttribute('x', bx0 + 5);
      txt.setAttribute('y', by0 + h - 3.5);
      txt.setAttribute('fill', '#e2e8f0');
      txt.setAttribute('font-size', '9');
      txt.setAttribute('font-family', 'sans-serif');
      txt.setAttribute('font-weight', '500');
      txt.textContent = lbl.text;

      // Full tooltip for truncated text
      if (lbl.full_text) {
        const titleElem = document.createElementNS('http://www.w3.org/2000/svg', 'title');
        titleElem.textContent = lbl.full_text;
        gLbl.appendChild(titleElem);
      }

      gLbl.appendChild(rect);
      gLbl.appendChild(txt);
      grp.appendChild(gLbl);
    });
  }

  renderDimensionsList() {
    const container = document.getElementById('dimensionsList');
    if (!container || !this.model) return;

    const q = (document.getElementById('dimsSearch')?.value || '').toLowerCase();
    const dims = (this.model.dimensions || []).filter(d => {
      if (!q) return true;
      return (d.title || '').toLowerCase().includes(q) || (d.group || '').toLowerCase().includes(q);
    });

    let html = '';
    let curGroup = '';
    for (const d of dims) {
      if (d.group !== curGroup) {
        curGroup = d.group;
        html += `<div class="font-bold text-slate-400 text-[11px] uppercase tracking-wider pt-2 border-t border-slate-800/80">${curGroup}</div>`;
      }
      const isSelected = this.selectedIds.has(d.id);
      const valStr = this.formatValue(d.value_pt, this.displayUnit, this.displayDecimals);
      const stateBadge = d.is_edited ? '<span class="text-[10px] text-cyan-400 font-bold">[Manual]</span>' : '<span class="text-[10px] text-slate-500">[Auto]</span>';

      html += `
        <div class="dim-row p-2 rounded-lg border ${isSelected ? 'border-blue-500 bg-blue-950/30' : 'border-slate-800 bg-slate-950/60 hover:bg-slate-900'} flex items-center justify-between cursor-pointer transition gap-2" data-dim-id="${d.id}" data-owner-id="${d.from_anchor || ''}">
          <div class="flex-1 truncate">
            <div class="font-semibold text-slate-200 truncate flex items-center space-x-1.5">
              <span>${d.title}</span> ${stateBadge}
            </div>
            <div class="text-[10px] text-slate-400 font-mono">${d.definition || ''}</div>
          </div>
          <div class="flex items-center space-x-1">
            <input type="number" step="0.01" value="${valStr}" class="dim-inline-input w-20 bg-slate-900 border border-slate-700 rounded px-1.5 py-0.5 text-right font-mono text-xs text-cyan-300 font-bold focus:ring-1 focus:ring-blue-500" data-dim-id="${d.id}">
            <span class="text-[11px] font-mono text-slate-400">${this.displayUnit}</span>
          </div>
        </div>
      `;
    }
    container.innerHTML = html;
    this.bindDimRowEvents();
  }

  bindDimRowEvents() {
    document.querySelectorAll('.dim-row').forEach(row => {
      const dimId = row.dataset.dimId;

      row.addEventListener('mouseenter', () => {
        this.setHovered(dimId);
      });

      row.addEventListener('mouseleave', () => {
        if (this.hoveredId === dimId) {
          this.setHovered(null);
        }
      });

      row.addEventListener('click', (e) => {
        if (e.target.matches('input')) return;
        this.setSelected(dimId, e.shiftKey);
      });
    });

    document.querySelectorAll('.dim-inline-input').forEach(input => {
      input.addEventListener('change', (e) => {
        const dimId = input.dataset.dimId;
        const newVal = parseFloat(input.value);
        const d = (this.model.dimensions || []).find(it => it.id === dimId);
        if (d && !isNaN(newVal)) {
          let ptVal = newVal;
          if (this.displayUnit === 'mm') ptVal = (newVal * 72.0) / 25.4;
          else if (this.displayUnit === 'px') ptVal = newVal / (this.model.dpi / 72.0);
          else if (this.displayUnit === 'in') ptVal = newVal * 72.0;

          d.value_pt = ptVal;
          d.source = 'manual';
          d.state = 'blue';
          d.is_edited = true;
          this.syncGeometryFromDimensions();
          this.saveHistory();
          this.render();
          this.renderDimensionsList();
        }
      });
    });
  }

  renderChecksList() {
    const empty = document.getElementById('checksListEmpty');
    const content = document.getElementById('checksListContent');
    const badge = document.getElementById('checksCountBadge');
    if (!empty || !content) return;

    const issues = [...(this.model.suspicious_objects || [])];

    // Surface lane_absent in Checks tab (Task 2)
    const laneAbsentReason = this.model.consistency?.checks?.lane_absent || this.model.dimension_lane?.lane_absent_reason;
    if (laneAbsentReason) {
      issues.unshift({
        id: 'chk_lane_absent',
        owner_id: 'target_table',
        title: 'Dimension Lane Absent',
        reason: laneAbsentReason,
      });
    }

    if (badge) badge.textContent = issues.length;

    if (issues.length === 0) {
      empty.classList.remove('hidden');
      content.classList.add('hidden');
      return;
    }

    empty.classList.add('hidden');
    content.classList.remove('hidden');

    let html = '';
    for (const item of issues) {
      html += `
        <div class="p-2.5 rounded-xl border border-amber-500/40 bg-amber-950/20 hover:bg-amber-950/40 cursor-pointer transition check-issue-card space-y-1" data-id="${item.id}" data-owner="${item.owner_id}">
          <div class="flex items-center space-x-2 text-amber-400 font-semibold text-xs">
            <i class="fa-solid fa-triangle-exclamation"></i>
            <span>${item.title}</span>
          </div>
          <p class="text-[11px] text-slate-300">${item.reason}</p>
        </div>
      `;
    }
    content.innerHTML = html;
  }

  setFocusTarget(target) {
    this.activeTarget = target;
    const sel = document.getElementById('focusTargetSelect');
    if (sel) sel.value = target;
    this.zoomFitTarget();
    this.render();
    this.renderDimensionsList();
  }

  zoomFitPage() {
    const vp = document.getElementById('viewport');
    if (!vp || !this.model) return;
    const docW = this.model.width_pt || 612;
    const docH = this.model.height_pt || 792;
    const padX = Math.max(28, vp.clientWidth * 0.04);
    const padY = Math.max(28, vp.clientHeight * 0.04);
    const availW = Math.max(100, vp.clientWidth - padX * 2);
    const availH = Math.max(100, vp.clientHeight - padY * 2);
    const scale = Math.min(availW / docW, availH / docH);
    this.zoom = Math.max(0.30, Math.min(8.0, scale));
    this.panX = Math.round((vp.clientWidth - (docW * this.zoom)) / 2.0);
    this.panY = Math.round((vp.clientHeight - (docH * this.zoom)) / 2.0);
    this.updateZoomDisplay();
    this.applyTransform();
  }

  zoomFitWidth() {
    const vp = document.getElementById('viewport');
    if (!vp || !this.model) return;
    const docW = this.model.width_pt || 612;
    const padX = Math.max(28, vp.clientWidth * 0.05);
    const availW = Math.max(100, vp.clientWidth - padX * 2);
    const scale = availW / docW;
    this.zoom = Math.max(0.30, Math.min(8.0, scale));
    this.panX = Math.round((vp.clientWidth - (docW * this.zoom)) / 2.0);
    this.panY = 28;
    this.updateZoomDisplay();
    this.applyTransform();
  }

  zoomFitTarget() {
    const vp = document.getElementById('viewport');
    if (!vp || !this.model) return;

    if (this.activeTarget === 'target_all') {
      this.zoomFitPage();
      return;
    }

    const targets = this.model.focus_targets || {};
    let tInfo = targets[this.activeTarget];
    if (!tInfo) {
      if (this.activeTarget === 'target_header' && targets['target_boxes']) tInfo = targets['target_boxes'];
      else if (targets['target_table']) tInfo = targets['target_table'];
      else {
        this.zoomFitPage();
        return;
      }
    }

    const [bx0, by0, bx1, by1] = tInfo.bbox_pt;
    const targetW = Math.max(60, bx1 - bx0);
    const targetH = Math.max(60, by1 - by0);

    const padX = Math.max(36, vp.clientWidth * 0.08);
    const padY = Math.max(36, vp.clientHeight * 0.08);
    const availW = Math.max(100, vp.clientWidth - padX * 2);
    const availH = Math.max(100, vp.clientHeight - padY * 2);

    const scale = Math.min(availW / targetW, availH / targetH);
    this.zoom = Math.max(0.35, Math.min(10.0, scale));

    const cx = (bx0 + bx1) / 2.0;
    const cy = (by0 + by1) / 2.0;

    this.panX = Math.round((vp.clientWidth / 2.0) - (cx * this.zoom));
    this.panY = Math.round((vp.clientHeight / 2.0) - (cy * this.zoom));

    this.updateZoomDisplay();
    this.applyTransform();
  }

  setZoom(newZoom) {
    const vp = document.getElementById('viewport');
    const vpW = vp ? vp.clientWidth : 800;
    const vpH = vp ? vp.clientHeight : 600;
    const oldZoom = this.zoom;
    const targetZoom = Math.max(0.30, Math.min(16.0, newZoom));
    const factor = targetZoom / oldZoom;
    this.zoomAtPoint(vpW / 2, vpH / 2, factor);
  }

  updateZoomDisplay() {
    const pct = `${Math.round(this.zoom * 100)}%`;
    const z1 = document.getElementById('zoomLevelDisplay');
    const z2 = document.getElementById('floatingZoomText');
    if (z1) z1.textContent = pct;
    if (z2) z2.textContent = pct;
  }

  zoomAtCenter(factor) {
    const vp = document.getElementById('viewport');
    const vpW = vp ? vp.clientWidth : 800;
    const vpH = vp ? vp.clientHeight : 600;
    this.zoomAtPoint(vpW / 2, vpH / 2, factor);
  }

  zoomAtPoint(screenX, screenY, factor) {
    const oldZoom = this.zoom;
    const newZoom = Math.max(0.30, Math.min(16.0, oldZoom * factor));
    if (Math.abs(newZoom - oldZoom) < 0.0001) return;

    this.panX = screenX - (screenX - this.panX) * (newZoom / oldZoom);
    this.panY = screenY - (screenY - this.panY) * (newZoom / oldZoom);
    this.zoom = newZoom;
    this.updateZoomDisplay();
    this.applyTransform();
  }

  applyTransform() {
    const container = document.getElementById('canvasTransformContainer');
    if (container) {
      container.style.transform = `translate3d(${this.panX}px, ${this.panY}px, 0px) scale(${this.zoom})`;
    }
  }

  toggleFullscreen() {
    this.isFullscreen = !this.isFullscreen;
    const workbench = this.container?.querySelector('.editor-workbench');
    if (workbench) {
      workbench.classList.toggle('fullscreen-workbench', this.isFullscreen);
    }
    const btnTop = document.getElementById('btnToggleFullscreen');
    const btnHud = document.getElementById('btnFloatingFullscreen');
    if (btnTop) {
      btnTop.innerHTML = this.isFullscreen
        ? '<i class="fa-solid fa-down-left-and-up-right-to-center text-[10px]"></i> <span>Restore</span>'
        : '<i class="fa-solid fa-up-right-and-down-left-from-center text-[10px]"></i> <span>Maximize</span>';
    }
    if (btnHud) {
      btnHud.innerHTML = this.isFullscreen
        ? '<i class="fa-solid fa-compress text-xs"></i>'
        : '<i class="fa-solid fa-expand text-xs"></i>';
    }
    setTimeout(() => {
      this.zoomFitPage();
    }, 100);
  }

  toggleSidebar() {
    this.isSidebarCollapsed = !this.isSidebarCollapsed;
    const sidebar = this.container?.querySelector('.editor-sidebar');
    if (sidebar) {
      sidebar.classList.toggle('collapsed', this.isSidebarCollapsed);
    }
    const btn = document.getElementById('btnToggleSidebar');
    if (btn) {
      btn.classList.toggle('bg-blue-600', this.isSidebarCollapsed);
      btn.classList.toggle('text-white', this.isSidebarCollapsed);
    }
    setTimeout(() => {
      this.zoomFitPage();
    }, 120);
  }

  bindEvents() {
    const vp = document.getElementById('viewport');
    if (vp) {
      vp.addEventListener('wheel', (e) => this.onWheel(e), { passive: false });
      vp.addEventListener('mousedown', (e) => this.onMouseDown(e));
      window.addEventListener('mousemove', (e) => this.onMouseMove(e));
      window.addEventListener('mouseup', (e) => this.onMouseUp(e));
    }

    window.addEventListener('keydown', (e) => {
      if (e.code === 'Space' && !e.target.matches('input, textarea, select')) {
        this.isSpacePressed = true;
        const vp = document.getElementById('viewport');
        if (vp && !this.isPanning) vp.style.cursor = 'grab';
      }
      this.onKeyDown(e);
    });

    window.addEventListener('keyup', (e) => {
      if (e.code === 'Space') {
        this.isSpacePressed = false;
        const vp = document.getElementById('viewport');
        if (vp && !this.isPanning) vp.style.cursor = this.activeTool === 'pan' ? 'grab' : 'default';
      }
    });

    window.addEventListener('resize', () => {
      if (this.model) {
        this.applyTransform();
      }
    });

    // Focus Target & Context Toggle
    document.getElementById('focusTargetSelect')?.addEventListener('change', (e) => {
      this.setFocusTarget(e.target.value);
    });
    document.getElementById('toggleShowContext')?.addEventListener('change', (e) => {
      this.showContext = e.target.checked;
      this.render();
    });

    // Page Selector & Analyze This Page Button
    document.getElementById('editorPageSelect')?.addEventListener('change', (e) => {
      const pageNum = parseInt(e.target.value, 10);
      if (pageNum && pageNum !== this.model?.page_number) {
        this.analyzePage(pageNum);
      }
    });

    document.getElementById('btnAnalyzeThisPage')?.addEventListener('click', () => {
      const select = document.getElementById('editorPageSelect');
      const pageNum = select ? parseInt(select.value, 10) : (this.model?.page_number || 1);
      this.analyzePage(pageNum);
    });

    // Tool Buttons
    document.getElementById('btnToolSelect')?.addEventListener('click', () => this.setTool('select'));
    document.getElementById('btnToolPan')?.addEventListener('click', () => this.setTool('pan'));
    document.getElementById('btnToolMeasure')?.addEventListener('click', () => this.setTool('measure'));
    document.getElementById('btnToggleSnap')?.addEventListener('click', () => this.toggleSnapping());
    document.getElementById('btnToggleCompare')?.addEventListener('click', () => {
      this.compareGhost = !this.compareGhost;
      document.getElementById('btnToggleCompare')?.classList.toggle('bg-amber-950/60', this.compareGhost);
      this.render();
    });

    // Action Bar Handlers
    document.getElementById('btnSnapAllColumns')?.addEventListener('click', () => this.snapAllColumns());
    document.getElementById('btnFitTableInk')?.addEventListener('click', () => this.fitTableInk());
    document.getElementById('btnDeduplicateGuides')?.addEventListener('click', () => this.deduplicateGuides());
    document.getElementById('btnCopyAIPrompt')?.addEventListener('click', () => this.copyAIPrompt());
    document.getElementById('btnCopyTemplateSpec')?.addEventListener('click', () => this.copyTemplatePreset());
    document.getElementById('btnCopyFitReport')?.addEventListener('click', () => this.copyFitReport());

    // Export Modal live format changes
    document.getElementById('exportFormatSelect')?.addEventListener('change', () => this.updateExportPreview());
    document.getElementById('exportPrivacySelect')?.addEventListener('change', (e) => {
      const isReal = e.target.value === 'real';
      const warn = document.getElementById('exportPrivacyWarning');
      if (warn) warn.classList.toggle('hidden', !isReal);
      this.updateExportPreview();
    });
    document.getElementById('exportUnitSelect')?.addEventListener('change', () => this.updateExportPreview());
    document.getElementById('exportDecimalsSelect')?.addEventListener('change', () => this.updateExportPreview());
    document.getElementById('exportIncludeDefs')?.addEventListener('change', () => this.updateExportPreview());

    // Zoom & Viewport Controls
    document.getElementById('btnZoomIn')?.addEventListener('click', () => this.zoomAtCenter(1.2));
    document.getElementById('btnZoomOut')?.addEventListener('click', () => this.zoomAtCenter(1 / 1.2));
    document.getElementById('btnZoomReset')?.addEventListener('click', () => this.setZoom(1.0));
    document.getElementById('btnZoomFitPage')?.addEventListener('click', () => this.zoomFitPage());
    document.getElementById('btnZoomFitWidth')?.addEventListener('click', () => this.zoomFitWidth());
    document.getElementById('btnZoomFitTarget')?.addEventListener('click', () => this.zoomFitTarget());
    document.getElementById('btnToggleSidebar')?.addEventListener('click', () => this.toggleSidebar());
    document.getElementById('btnToggleFullscreen')?.addEventListener('click', () => this.toggleFullscreen());

    document.getElementById('btnFloatingZoomIn')?.addEventListener('click', () => this.zoomAtCenter(1.2));
    document.getElementById('btnFloatingZoomOut')?.addEventListener('click', () => this.zoomAtCenter(1 / 1.2));
    document.getElementById('btnFloatingZoomReset')?.addEventListener('click', () => this.setZoom(1.0));
    document.getElementById('btnFloatingFitPage')?.addEventListener('click', () => this.zoomFitPage());
    document.getElementById('btnFloatingFitWidth')?.addEventListener('click', () => this.zoomFitWidth());
    document.getElementById('btnFloatingFitTarget')?.addEventListener('click', () => this.zoomFitTarget());
    document.getElementById('btnFloatingFullscreen')?.addEventListener('click', () => this.toggleFullscreen());

    document.getElementById('btnAddVGuide')?.addEventListener('click', () => this.addGuide('V'));
    document.getElementById('btnAddHGuide')?.addEventListener('click', () => this.addGuide('H'));
    document.getElementById('btnDeleteSelected')?.addEventListener('click', () => this.deleteSelected());

    document.getElementById('btnUndo')?.addEventListener('click', () => this.undo());
    document.getElementById('btnRedo')?.addEventListener('click', () => this.redo());

    document.getElementById('btnSaveEdits')?.addEventListener('click', () => this.saveEditsToBackend());
    document.getElementById('btnCopyAllDims')?.addEventListener('click', () => this.copyAllDimensions());
    document.getElementById('btnOpenExportModal')?.addEventListener('click', () => this.openExportModal());
    document.getElementById('btnCloseExportModal')?.addEventListener('click', () => this.closeExportModal());
    document.getElementById('btnConfirmCopy')?.addEventListener('click', () => this.confirmCopyModal());
    document.getElementById('btnDownloadExportFile')?.addEventListener('click', () => this.downloadExportFile());

    document.getElementById('dimsSearch')?.addEventListener('input', () => this.renderDimensionsList());
    document.getElementById('unitSelect')?.addEventListener('change', (e) => { this.displayUnit = e.target.value; this.renderDimensionsList(); });
    document.getElementById('decimalsSelect')?.addEventListener('change', (e) => { this.displayDecimals = Number(e.target.value); this.renderDimensionsList(); });

    // Tabs switching
    document.getElementById('tabBtnDims')?.addEventListener('click', () => this.switchTab('tabPanelDims'));
    document.getElementById('tabBtnChecks')?.addEventListener('click', () => this.switchTab('tabPanelChecks'));
    document.getElementById('tabBtnProps')?.addEventListener('click', () => this.switchTab('tabPanelProps'));

    // Properties input bindings
    this.bindPropertyInputs();
  }

  bindPropertyInputs() {
    ['propInputTitle', 'propInputX0', 'propInputY0', 'propInputW', 'propInputH'].forEach(id => {
      document.getElementById(id)?.addEventListener('input', () => this.syncObjectFromProperties());
    });
  }

  syncObjectFromProperties() {
    if (this.selectedIds.size === 0) return;
    const firstId = Array.from(this.selectedIds)[0];
    const guide = (this.model.guides || []).find(g => g.id === firstId);
    const box = (this.model.boxes || []).find(b => b.id === firstId);
    const isTable = firstId === 'target_table' || firstId === 'table' || firstId === 'table_grid' || firstId.startsWith('dim_table_');
    const isRow = firstId.startsWith('row_') || firstId.startsWith('dim_row_');

    const title = document.getElementById('propInputTitle')?.value || '';
    const x0 = parseFloat(document.getElementById('propInputX0')?.value || 0);
    const y0 = parseFloat(document.getElementById('propInputY0')?.value || 0);
    const w = parseFloat(document.getElementById('propInputW')?.value || 0);
    const h = parseFloat(document.getElementById('propInputH')?.value || 0);

    if (guide) {
      guide.title = title;
      if (guide.orientation === 'V') guide.position_pt = x0;
      else guide.position_pt = y0;
      guide.source = 'manual';
      guide.state = 'blue';
      guide.is_edited = true;
      this.syncColumnsFromGuides();
    } else if (box) {
      box.title = title;
      box.x0_pt = x0;
      box.y0_pt = y0;
      box.width_pt = Math.max(1, w);
      box.height_pt = Math.max(1, h);
      box.x1_pt = box.x0_pt + box.width_pt;
      box.y1_pt = box.y0_pt + box.height_pt;
    } else if (isTable && this.model.table_bbox) {
      const dx = x0 - this.model.table_bbox.x0_pt;
      const dy = y0 - this.model.table_bbox.y0_pt;
      this.model.table_bbox.x0_pt = x0;
      this.model.table_bbox.y0_pt = y0;
      this.model.table_bbox.width_pt = Math.max(10, w || this.model.table_bbox.width_pt);
      this.model.table_bbox.height_pt = Math.max(10, h || this.model.table_bbox.height_pt);
      this.model.table_bbox.x1_pt = this.model.table_bbox.x0_pt + this.model.table_bbox.width_pt;
      this.model.table_bbox.y1_pt = this.model.table_bbox.y0_pt + this.model.table_bbox.height_pt;
      
      // Shift child table elements if moved
      if (dx !== 0 || dy !== 0) {
        (this.model.guides || []).forEach(g => {
          if (g.owner_id === 'target_table' || g.owner_id === 'target_columns' || g.owner_id === 'target_rows') {
            if (g.orientation === 'V') { g.position_pt += dx; if (g.start_pt != null) g.start_pt += dy; if (g.end_pt != null) g.end_pt += dy; }
            else { g.position_pt += dy; if (g.start_pt != null) g.start_pt += dx; if (g.end_pt != null) g.end_pt += dx; }
            g.is_edited = true;
          }
        });
        (this.model.columns || []).forEach(c => { c.x0_pt += dx; c.x1_pt += dx; });
        (this.model.rows || []).forEach(r => { r.y0_pt += dy; r.y1_pt += dy; });
      }
      this.syncTableDimensions();
    } else if (isRow && this.model.rows) {
      const rIdx = parseInt(firstId.replace('row_', '').replace('dim_row_', ''), 10);
      if (!isNaN(rIdx) && this.model.rows[rIdx]) {
        const r = this.model.rows[rIdx];
        r.y0_pt = y0;
        if (h > 0) {
          r.pitch_pt = h;
          r.y1_pt = r.y0_pt + h;
        }
        this.syncRowDimensions();
      }
    }

    this.render();
    this.renderDimensionsList();
  }

  switchTab(tabId) {
    document.querySelectorAll('#tabPanelDims, #tabPanelChecks, #tabPanelProps').forEach(p => p.classList.add('hidden'));
    document.getElementById(tabId)?.classList.remove('hidden');
    document.querySelectorAll('#tabBtnDims, #tabBtnChecks, #tabBtnProps').forEach(b => {
      b.classList.remove('border-b-2', 'border-blue-500', 'text-blue-400', 'bg-slate-900/60');
      b.classList.add('text-slate-400');
    });
    if (tabId === 'tabPanelDims') document.getElementById('tabBtnDims')?.classList.add('border-b-2', 'border-blue-500', 'text-blue-400', 'bg-slate-900/60');
    if (tabId === 'tabPanelChecks') document.getElementById('tabBtnChecks')?.classList.add('border-b-2', 'border-blue-500', 'text-blue-400', 'bg-slate-900/60');
    if (tabId === 'tabPanelProps') document.getElementById('tabBtnProps')?.classList.add('border-b-2', 'border-blue-500', 'text-blue-400', 'bg-slate-900/60');
  }

  setTool(tool) {
    this.activeTool = tool;
    document.querySelectorAll('.tool-btn').forEach(b => b.classList.remove('active', 'bg-blue-600', 'text-white'));
    if (tool === 'select') document.getElementById('btnToolSelect')?.classList.add('active', 'bg-blue-600', 'text-white');
    if (tool === 'pan') document.getElementById('btnToolPan')?.classList.add('active', 'bg-blue-600', 'text-white');
    if (tool === 'measure') document.getElementById('btnToolMeasure')?.classList.add('active', 'bg-blue-600', 'text-white');

    const vp = document.getElementById('viewport');
    if (vp) {
      if (tool === 'pan') vp.style.cursor = 'grab';
      else if (tool === 'select') vp.style.cursor = 'default';
      else vp.style.cursor = 'crosshair';
    }
  }

  toggleSnapping() {
    this.snapping.enabled = !this.snapping.enabled;
    const btn = document.getElementById('btnToggleSnap');
    if (btn) {
      btn.innerHTML = this.snapping.enabled
        ? '<i class="fa-solid fa-magnet"></i> <span>Snap: ON</span>'
        : '<i class="fa-solid fa-magnet text-slate-500"></i> <span>Snap: OFF</span>';
    }
  }

  onWheel(e) {
    e.preventDefault();
    const vp = document.getElementById('viewport');
    const vpRect = vp ? vp.getBoundingClientRect() : { left: 0, top: 0 };
    const mouseX = e.clientX - vpRect.left;
    const mouseY = e.clientY - vpRect.top;

    let factor;
    if (Math.abs(e.deltaY) < 40) {
      // Precision trackpad pinch / fine scroll
      factor = Math.exp(-e.deltaY * 0.005);
    } else {
      // Smooth mouse wheel step
      factor = e.deltaY < 0 ? 1.09 : (1 / 1.09);
    }
    this.zoomAtPoint(mouseX, mouseY, factor);
  }

  startUnifiedDrag(clickedId, pt, isShift = false) {
    if (isShift) {
      if (this.selectedIds.has(clickedId)) this.selectedIds.delete(clickedId);
      else this.selectedIds.add(clickedId);
    } else {
      if (!this.selectedIds.has(clickedId) || this.selectedIds.size <= 1) {
        this.selectedIds.clear();
        if (clickedId) this.selectedIds.add(clickedId);
      }
    }

    if (this.selectedIds.size > 1) {
      const selectedGuides = (this.model.guides || []).filter(g => this.selectedIds.has(g.id));
      const selectedBoxes = (this.model.boxes || []).filter(b => this.selectedIds.has(b.id));
      const selectedRows = [];
      (this.model.rows || []).forEach((r, idx) => {
        if (this.selectedIds.has(`row_${idx}`) || this.selectedIds.has(r.id) || this.selectedIds.has(`dim_row_${idx}_pitch`)) {
          selectedRows.push({ idx, ...r });
        }
      });
      const selectedCols = [];
      (this.model.columns || []).forEach((c) => {
        const colId = `col_${c.column_index}`;
        if (this.selectedIds.has(colId) || this.selectedIds.has(`dim_col_${c.column_index}_width`)) {
          selectedCols.push({ ...c });
        }
      });
      const isTableSelected = this.selectedIds.has('target_table') || this.selectedIds.has('table') || this.selectedIds.has('table_grid');

      this.dragState = {
        type: 'multi_element',
        origGuides: selectedGuides.map(g => ({ ...g })),
        origBoxes: selectedBoxes.map(b => ({ ...b })),
        origRows: selectedRows,
        origCols: selectedCols,
        origTable: isTableSelected ? { ...this.model.table_bbox } : null,
        origTableGuides: isTableSelected ? (this.model.guides || []).map(g => ({ ...g })) : null,
        origTableCols: isTableSelected ? (this.model.columns || []).map(c => ({ ...c })) : null,
        origTableRows: isTableSelected ? (this.model.rows || []).map(r => ({ ...r })) : null,
        origLane: this.model.dimension_lane ? JSON.parse(JSON.stringify(this.model.dimension_lane)) : null,
        startPt: pt
      };
    } else if (this.selectedIds.size === 1) {
      const id = Array.from(this.selectedIds)[0];
      const g = (this.model.guides || []).find(it => it.id === id);
      const b = (this.model.boxes || []).find(it => it.id === id);
      const isTable = id === 'target_table' || id === 'table' || id === 'table_grid';
      const isRow = id.startsWith('row_') || id.startsWith('dim_row_');
      const isCol = id.startsWith('col_') || id.startsWith('dim_col_');

      if (g) {
        this.dragState = { type: 'guide', id: g.id, origGuide: { ...g }, startPt: pt };
      } else if (b) {
        this.dragState = { type: 'box', id: b.id, origBox: { ...b }, startPt: pt };
      } else if (isTable) {
        this.dragState = {
          type: 'table',
          origTable: { ...this.model.table_bbox },
          origGuides: (this.model.guides || []).map(g => ({ ...g })),
          origCols: (this.model.columns || []).map(c => ({ ...c })),
          origRows: (this.model.rows || []).map(r => ({ ...r })),
          origLane: this.model.dimension_lane ? JSON.parse(JSON.stringify(this.model.dimension_lane)) : null,
          startPt: pt
        };
      } else if (isRow) {
        const rIdx = parseInt(id.replace('row_', '').replace('dim_row_', ''), 10);
        const r = (this.model.rows && !isNaN(rIdx)) ? this.model.rows[rIdx] : null;
        if (r) {
          this.dragState = {
            type: 'row',
            rowIndex: rIdx,
            origRow: { ...r },
            origPrevRow: (rIdx > 0 && this.model.rows) ? { ...this.model.rows[rIdx - 1] } : null,
            origNextRow: (this.model.rows && rIdx < this.model.rows.length - 1) ? { ...this.model.rows[rIdx + 1] } : null,
            startPt: pt
          };
        }
      } else if (isCol) {
        const cIdx = parseInt(id.replace('col_', '').replace('dim_col_', '').replace('_width', ''), 10);
        const col = (this.model.columns && this.model.columns.find(it => it.column_index === cIdx));
        if (col) {
          this.dragState = {
            type: 'col',
            colIndex: cIdx,
            origCol: { ...col },
            origTable: { ...this.model.table_bbox },
            origGuides: (this.model.guides || []).map(g => ({ ...g })),
            startPt: pt
          };
        }
      }
    }
    this.render();
    this.renderDimensionsList();
    this.showPropertiesPanel();
    this.scrollLinkedSidebarItemIntoView(clickedId);
  }

  onMouseDown(e) {
    if (this.isSpacePressed || e.button === 1 || this.activeTool === 'pan') {
      this.isPanning = true;
      this.panStart = { x: e.clientX - this.panX, y: e.clientY - this.panY };
      const vp = document.getElementById('viewport');
      if (vp) vp.style.cursor = 'grabbing';
      return;
    }

    const svg = document.getElementById('editorSvg');
    const pt = this.transform.screenToPt(e.clientX, e.clientY, svg?.getBoundingClientRect());
    const isShift = e.shiftKey || e.ctrlKey || e.metaKey;
    const target = e.target;

    // Box Resize Handle Drag
    if (target.classList.contains('box-resize-handle')) {
      const boxId = target.dataset.boxId;
      const hType = target.dataset.handleType;
      const b = (this.model.boxes || []).find(it => it.id === boxId);
      if (b) {
        this.dragState = {
          type: 'box_handle',
          boxId,
          handleType: hType,
          origBox: { ...b },
          startPt: pt
        };
        return;
      }
    }

    // Endpoint Handle Drag
    if (target.classList.contains('endpoint-handle')) {
      const gId = target.dataset.guideId;
      const hType = target.dataset.handleType;
      this.dragState = { type: 'endpoint', guideId: gId, handleType: hType, startPt: pt };
      return;
    }

    // Whole Table Drag (via boundary rect or header drag tab)
    if (target.classList.contains('table-boundary-rect') || target.classList.contains('table-drag-bar')) {
      this.startUnifiedDrag('target_table', pt, isShift);
      return;
    }

    // Row Hit Line, Separator, or Band Drag
    if (target.classList.contains('row-hit-line') || target.classList.contains('row-separator-line') || target.classList.contains('row-band')) {
      const rIdx = parseInt(target.dataset.rowIndex, 10);
      const rId = target.dataset.id || `row_${rIdx}`;
      this.startUnifiedDrag(rId, pt, isShift);
      return;
    }

    // Column Rect Drag
    if (target.classList.contains('column-rect')) {
      const colId = target.dataset.id;
      this.startUnifiedDrag(colId, pt, isShift);
      return;
    }

    // Guide Drag (via hit-area or line)
    if (target.classList.contains('guide-hit-area') || target.classList.contains('guide-line')) {
      const gId = target.dataset.id;
      this.startUnifiedDrag(gId, pt, isShift);
      return;
    }

    // Box Drag (Header, Container, Logo, Footer)
    if (target.classList.contains('box-element')) {
      const bId = target.dataset.id;
      this.startUnifiedDrag(bId, pt, isShift);
      return;
    }

    // Measure Tool
    if (this.activeTool === 'measure') {
      this.measurePoints.push(pt);
      if (this.measurePoints.length === 2) this.finishMeasure();
      return;
    }

    // Clear selection on empty canvas click
    this.selectedIds.clear();
    this.render();
    this.renderDimensionsList();
    this.showPropertiesPanel();
  }

  onMouseMove(e) {
    if (this.isPanning) {
      this.panX = e.clientX - this.panStart.x;
      this.panY = e.clientY - this.panStart.y;
      this.applyTransform();
      return;
    }

    const svg = document.getElementById('editorSvg');
    const rawPt = this.transform.screenToPt(e.clientX, e.clientY, svg?.getBoundingClientRect());
    
    // Snapping resolution against SnapIndex
    const snap = this.snapping.resolveSnap(rawPt.x, rawPt.y, this.model, this.zoom, e.ctrlKey);
    this.updateStatusBar(rawPt.x, rawPt.y, snap);

    if (this.dragState) {
      const activeX = snap.x;
      const activeY = snap.y;

      if (this.dragState.type === 'table') {
        const dx = activeX - this.dragState.startPt.x;
        const dy = activeY - this.dragState.startPt.y;
        const origT = this.dragState.origTable;
        if (this.model.table_bbox && origT) {
          this.model.table_bbox.x0_pt = origT.x0_pt + dx;
          this.model.table_bbox.y0_pt = origT.y0_pt + dy;
          this.model.table_bbox.x1_pt = origT.x1_pt + dx;
          this.model.table_bbox.y1_pt = origT.y1_pt + dy;
          this.model.table_bbox.width_pt = origT.width_pt;
          this.model.table_bbox.height_pt = origT.height_pt;

          // Translate table guides
          if (this.model.guides && this.dragState.origGuides) {
            for (let i = 0; i < this.model.guides.length; i++) {
              const g = this.model.guides[i];
              const og = this.dragState.origGuides[i];
              if (og && (g.owner_id === 'target_table' || g.owner_id === 'target_columns' || g.owner_id === 'target_rows')) {
                if (g.orientation === 'V') {
                  g.position_pt = og.position_pt + dx;
                  if (og.start_pt != null) g.start_pt = og.start_pt + dy;
                  if (og.end_pt != null) g.end_pt = og.end_pt + dy;
                } else {
                  g.position_pt = og.position_pt + dy;
                  if (og.start_pt != null) g.start_pt = og.start_pt + dx;
                  if (og.end_pt != null) g.end_pt = og.end_pt + dx;
                }
                g.is_edited = true;
              }
            }
          }

          // Translate columns
          if (this.model.columns && this.dragState.origCols) {
            for (let i = 0; i < this.model.columns.length; i++) {
              const c = this.model.columns[i];
              const oc = this.dragState.origCols[i];
              if (oc) {
                c.x0_pt = oc.x0_pt + dx;
                c.x1_pt = oc.x1_pt + dx;
              }
            }
          }

          // Translate rows
          if (this.model.rows && this.dragState.origRows) {
            for (let i = 0; i < this.model.rows.length; i++) {
              const r = this.model.rows[i];
              const or = this.dragState.origRows[i];
              if (or) {
                r.y0_pt = or.y0_pt + dy;
                r.y1_pt = or.y1_pt + dy;
              }
            }
          }

          // Translate dimension lane
          if (this.model.dimension_lane && this.dragState.origLane) {
            const lane = this.model.dimension_lane;
            const ol = this.dragState.origLane;
            if (ol.lane_y_pt != null) lane.lane_y_pt = ol.lane_y_pt + dy;
            if (lane.arrows && ol.arrows) {
              lane.arrows.forEach((a, idx) => {
                if (ol.arrows[idx]) {
                  a.x0_pt = ol.arrows[idx].x0_pt + dx;
                  a.x1_pt = ol.arrows[idx].x1_pt + dx;
                }
              });
            }
            if (lane.extension_lines && ol.extension_lines) {
              lane.extension_lines.forEach((el, idx) => {
                if (ol.extension_lines[idx]) {
                  el.x_pt = ol.extension_lines[idx].x_pt + dx;
                  el.y0_pt = ol.extension_lines[idx].y0_pt + dy;
                  el.y1_pt = ol.extension_lines[idx].y1_pt + dy;
                }
              });
            }
            if (lane.numbered_markers && ol.numbered_markers) {
              lane.numbered_markers.forEach((m, idx) => {
                if (ol.numbered_markers[idx]) {
                  m.x_pt = ol.numbered_markers[idx].x_pt + dx;
                  m.y_pt = ol.numbered_markers[idx].y_pt + dy;
                }
              });
            }
          }

          this.syncTableDimensions();
          this.render();
          this.showPropertiesPanel();
        }
      } else if (this.dragState.type === 'multi_element' || this.dragState.type === 'multi_guide') {
        const dx = activeX - this.dragState.startPt.x;
        const dy = activeY - this.dragState.startPt.y;

        // 1. Move all selected guides simultaneously, locking relative spacing
        if (this.dragState.origGuides && this.dragState.origGuides.length > 0) {
          this.dragState.origGuides.forEach(og => {
            const g = (this.model.guides || []).find(it => it.id === og.id);
            if (g && !g.locked) {
              if (g.orientation === 'V') {
                g.position_pt = og.position_pt + dx;
              } else {
                g.position_pt = og.position_pt + dy;
              }
              g.source = (snap.snappedX || snap.snappedY) ? 'snapped' : 'manual';
              g.state = (snap.snappedX || snap.snappedY) ? 'green' : 'blue';
              g.is_edited = true;
            }
          });
          this.syncColumnsFromGuides();
        }

        // 2. Move all selected boxes simultaneously
        if (this.dragState.origBoxes && this.dragState.origBoxes.length > 0) {
          this.dragState.origBoxes.forEach(ob => {
            const b = (this.model.boxes || []).find(it => it.id === ob.id);
            if (b) {
              b.x0_pt = ob.x0_pt + dx;
              b.y0_pt = ob.y0_pt + dy;
              b.x1_pt = ob.x1_pt + dx;
              b.y1_pt = ob.y1_pt + dy;
            }
          });
        }

        // 3. Move all selected rows simultaneously
        if (this.dragState.origRows && this.dragState.origRows.length > 0) {
          this.dragState.origRows.forEach(or => {
            const r = (this.model.rows && this.model.rows[or.idx]);
            if (r) {
              r.y0_pt = or.y0_pt + dy;
              if (or.y1_pt != null) r.y1_pt = or.y1_pt + dy;
            }
          });
          this.syncRowDimensions();
        }

        // 4. Move all selected columns simultaneously
        if (this.dragState.origCols && this.dragState.origCols.length > 0) {
          this.dragState.origCols.forEach(oc => {
            const c = (this.model.columns || []).find(it => it.column_index === oc.column_index);
            if (c) {
              c.x0_pt = oc.x0_pt + dx;
              c.x1_pt = oc.x1_pt + dx;
            }
          });
        }

        // 4. Move table if selected
        if (this.dragState.origTable && this.model.table_bbox) {
          const origT = this.dragState.origTable;
          this.model.table_bbox.x0_pt = origT.x0_pt + dx;
          this.model.table_bbox.y0_pt = origT.y0_pt + dy;
          this.model.table_bbox.x1_pt = origT.x1_pt + dx;
          this.model.table_bbox.y1_pt = origT.y1_pt + dy;
          this.model.table_bbox.width_pt = origT.width_pt;
          this.model.table_bbox.height_pt = origT.height_pt;

          if (this.model.guides && this.dragState.origTableGuides) {
            for (let i = 0; i < this.model.guides.length; i++) {
              const g = this.model.guides[i];
              const og = this.dragState.origTableGuides[i];
              if (og && (g.owner_id === 'target_table' || g.owner_id === 'target_columns' || g.owner_id === 'target_rows')) {
                if (g.orientation === 'V') {
                  g.position_pt = og.position_pt + dx;
                  if (og.start_pt != null) g.start_pt = og.start_pt + dy;
                  if (og.end_pt != null) g.end_pt = og.end_pt + dy;
                } else {
                  g.position_pt = og.position_pt + dy;
                  if (og.start_pt != null) g.start_pt = og.start_pt + dx;
                  if (og.end_pt != null) g.end_pt = og.end_pt + dx;
                }
                g.is_edited = true;
              }
            }
          }

          if (this.model.columns && this.dragState.origTableCols) {
            for (let i = 0; i < this.model.columns.length; i++) {
              const c = this.model.columns[i];
              const oc = this.dragState.origTableCols[i];
              if (oc) {
                c.x0_pt = oc.x0_pt + dx;
                c.x1_pt = oc.x1_pt + dx;
              }
            }
          }

          if (this.model.rows && this.dragState.origTableRows) {
            for (let i = 0; i < this.model.rows.length; i++) {
              const r = this.model.rows[i];
              const or = this.dragState.origTableRows[i];
              if (or) {
                r.y0_pt = or.y0_pt + dy;
                r.y1_pt = or.y1_pt + dy;
              }
            }
          }

          if (this.model.dimension_lane && this.dragState.origLane) {
            const lane = this.model.dimension_lane;
            const ol = this.dragState.origLane;
            if (ol.lane_y_pt != null) lane.lane_y_pt = ol.lane_y_pt + dy;
            if (lane.arrows && ol.arrows) {
              lane.arrows.forEach((a, idx) => {
                if (ol.arrows[idx]) {
                  a.x0_pt = ol.arrows[idx].x0_pt + dx;
                  a.x1_pt = ol.arrows[idx].x1_pt + dx;
                }
              });
            }
          }
          this.syncTableDimensions();
        }

        this.render();
        this.showPropertiesPanel();
      } else if (this.dragState.type === 'row') {
        const rIdx = this.dragState.rowIndex;
        const r = (this.model.rows && !isNaN(rIdx)) ? this.model.rows[rIdx] : null;
        if (r) {
          const dy = activeY - this.dragState.startPt.y;
          const origR = this.dragState.origRow;
          r.y0_pt = origR.y0_pt + dy;
          if (origR.y1_pt != null) {
            r.y1_pt = origR.y1_pt + dy;
          }
          if (rIdx > 0 && this.model.rows[rIdx - 1]) {
            this.model.rows[rIdx - 1].y1_pt = r.y0_pt;
            this.model.rows[rIdx - 1].pitch_pt = Math.max(0.1, this.model.rows[rIdx - 1].y1_pt - this.model.rows[rIdx - 1].y0_pt);
          }
          if (r.y1_pt != null && r.y0_pt != null) {
            r.pitch_pt = Math.max(0.1, r.y1_pt - r.y0_pt);
          }
          this.syncRowDimensions();
          this.render();
          this.showPropertiesPanel();
        }
      } else if (this.dragState.type === 'guide') {
        const g = (this.model.guides || []).find(it => it.id === this.dragState.id);
        if (g && !g.locked) {
          if (g.orientation === 'V') g.position_pt = activeX;
          else g.position_pt = activeY;
          g.source = (snap.snappedX || snap.snappedY) ? 'snapped' : 'manual';
          g.state = (snap.snappedX || snap.snappedY) ? 'green' : 'blue';
          g.is_edited = true;
          this.syncColumnsFromGuides();
          this.render();
          this.showPropertiesPanel();
        }
      } else if (this.dragState.type === 'col') {
        const c = (this.model.columns || []).find(it => it.column_index === this.dragState.colIndex);
        const orig = this.dragState.origCol;
        if (c && orig) {
          const dx = activeX - this.dragState.startPt.x;
          c.x0_pt = orig.x0_pt + dx;
          c.x1_pt = orig.x1_pt + dx;
          this.render();
          this.showPropertiesPanel();
        }
      } else if (this.dragState.type === 'endpoint') {
        const g = (this.model.guides || []).find(it => it.id === this.dragState.guideId);
        if (g && !g.locked) {
          if (this.dragState.handleType === 'start_v') g.start_pt = activeY;
          else if (this.dragState.handleType === 'end_v') g.end_pt = activeY;
          else if (this.dragState.handleType === 'start_h') g.start_pt = activeX;
          else if (this.dragState.handleType === 'end_h') g.end_pt = activeX;
          g.source = 'manual';
          g.state = 'blue';
          g.is_edited = true;
          this.render();
        }
      } else if (this.dragState.type === 'box') {
        const b = (this.model.boxes || []).find(it => it.id === this.dragState.id);
        const orig = this.dragState.origBox;
        if (b && orig) {
          const dx = activeX - this.dragState.startPt.x;
          const dy = activeY - this.dragState.startPt.y;
          b.x0_pt = orig.x0_pt + dx;
          b.y0_pt = orig.y0_pt + dy;
          b.x1_pt = orig.x1_pt + dx;
          b.y1_pt = orig.y1_pt + dy;
          this.render();
          this.showPropertiesPanel();
        }
      } else if (this.dragState.type === 'box_handle') {
        const b = (this.model.boxes || []).find(it => it.id === this.dragState.boxId);
        const orig = this.dragState.origBox;
        const ht = this.dragState.handleType;
        if (b && orig) {
          if (ht.includes('w')) b.x0_pt = Math.min(orig.x1_pt - 5, activeX);
          if (ht.includes('e')) b.x1_pt = Math.max(orig.x0_pt + 5, activeX);
          if (ht.includes('n')) b.y0_pt = Math.min(orig.y1_pt - 5, activeY);
          if (ht.includes('s')) b.y1_pt = Math.max(orig.y0_pt + 5, activeY);
          b.width_pt = b.x1_pt - b.x0_pt;
          b.height_pt = b.y1_pt - b.y0_pt;
          this.render();
          this.showPropertiesPanel();
        }
      }
    } else {
      // Hover detection across interactive canvas elements
      const target = e.target;
      if (target && target.closest) {
        const interactive = target.closest('[data-id], .table-boundary-rect, .table-drag-bar, .column-rect, .row-separator-line, .row-band, .guide-line, .box-element');
        if (interactive) {
          const hoverId = interactive.dataset.id || interactive.dataset.boxId || interactive.dataset.guideId;
          this.setHovered(hoverId);
        } else {
          this.setHovered(null);
        }
      }
    }
  }

  onMouseUp(e) {
    if (this.isPanning) {
      this.isPanning = false;
      const vp = document.getElementById('viewport');
      if (vp) vp.style.cursor = this.activeTool === 'pan' ? 'grab' : 'default';
    }

    if (this.dragState) {
      this.saveHistory();
      this.dragState = null;
      this.renderDimensionsList();
      this.renderChecksList();
    }
  }

  syncTableDimensions() {
    if (!this.model.table_bbox) return;
    const t = this.model.table_bbox;
    const dims = this.model.dimensions || [];
    const tW = dims.find(d => d.id === 'dim_table_width');
    if (tW) { tW.value_pt = t.width_pt; tW.is_edited = true; }
    const tH = dims.find(d => d.id === 'dim_table_height');
    if (tH) { tH.value_pt = t.height_pt; tH.is_edited = true; }
    const tTop = dims.find(d => d.id === 'dim_table_top_margin');
    if (tTop) { tTop.value_pt = t.y0_pt; tTop.is_edited = true; }
    const tLeft = dims.find(d => d.id === 'dim_table_left_margin');
    if (tLeft) { tLeft.value_pt = t.x0_pt; tLeft.is_edited = true; }
    const tBottom = dims.find(d => d.id === 'dim_table_bottom_margin');
    if (tBottom) { tBottom.value_pt = Math.max(0, this.model.height_pt - t.y1_pt); tBottom.is_edited = true; }
  }

  syncRowDimensions() {
    if (!this.model.rows || this.model.rows.length === 0) return;
    const avgPitch = this.model.rows.reduce((acc, r) => acc + (r.pitch_pt || 0), 0) / this.model.rows.length;
    const dims = this.model.dimensions || [];
    const rDim = dims.find(d => d.id === 'dim_row_pitch' || d.id === 'dim_body_row_pitch');
    if (rDim && avgPitch > 0) {
      rDim.value_pt = avgPitch;
      rDim.is_edited = true;
    }
  }

  onKeyDown(e) {
    if (['1', '2', '3', '4'].includes(e.key) && !e.target.matches('input, textarea')) {
      e.preventDefault();
      this.setZoom(Number(e.key));
      return;
    }
    if ((e.key === '0') && !e.target.matches('input, textarea')) {
      e.preventDefault();
      this.zoomFitPage();
      return;
    }
    if ((e.key === 'w' || e.key === 'W') && !e.target.matches('input, textarea') && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      this.zoomFitWidth();
      return;
    }
    if ((e.key === 'f' || e.key === 'F') && !e.target.matches('input, textarea') && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      this.zoomFitTarget();
      return;
    }
    if ((e.key === 'b' || e.key === 'B') && !e.target.matches('input, textarea') && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      this.toggleSidebar();
      return;
    }
    if (e.key === 'Escape') {
      if (this.isFullscreen) {
        this.toggleFullscreen();
        return;
      }
    }
    if (['+', '='].includes(e.key) && !e.target.matches('input, textarea')) {
      e.preventDefault();
      this.zoomAtCenter(1.2);
      return;
    }
    if (['-', '_'].includes(e.key) && !e.target.matches('input, textarea')) {
      e.preventDefault();
      this.zoomAtCenter(1 / 1.2);
      return;
    }
    if ((e.key === 's' || e.key === 'S') && !e.target.matches('input, textarea') && !e.ctrlKey && !e.metaKey) {
      this.toggleSnapping();
      return;
    }
    if (e.key === 'Tab' && !e.target.matches('input, textarea')) {
      e.preventDefault();
      this.stepThroughSelection(e.shiftKey ? -1 : 1);
      return;
    }
    if ((e.key === 'Delete' || e.key === 'Backspace') && !e.target.matches('input, textarea')) {
      this.deleteSelected();
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
      e.preventDefault();
      this.undo();
    }
    if ((e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === 'y' || (e.shiftKey && e.key.toLowerCase() === 'z'))) {
      e.preventDefault();
      this.redo();
    }
  }

  stepThroughSelection(step = 1) {
    const visibleGuides = (this.model.guides || []).filter(g => this.isObjectInFocus(g.owner_id));
    if (visibleGuides.length === 0) return;

    let curIdx = visibleGuides.findIndex(g => this.selectedIds.has(g.id));
    let nextIdx = (curIdx + step + visibleGuides.length) % visibleGuides.length;
    this.selectedIds.clear();
    this.selectedIds.add(visibleGuides[nextIdx].id);
    this.render();
    this.renderDimensionsList();
    this.showPropertiesPanel();
  }

  updateStatusBar(xPt, yPt, snap) {
    const curPt = document.getElementById('statusBarCursorPt');
    const curMm = document.getElementById('statusBarCursorMm');
    const snapTarget = document.getElementById('statusBarSnapTarget');
    const multiSel = document.getElementById('statusBarMultiSelect');
    const multiSelTxt = document.getElementById('statusBarMultiSelectText');

    if (curPt) curPt.textContent = `Cursor: ${xPt.toFixed(2)} pt, ${yPt.toFixed(2)} pt`;
    if (curMm) curMm.textContent = `${this.transform.ptToMm(xPt).toFixed(2)} mm, ${this.transform.ptToMm(yPt).toFixed(2)} mm`;

    if (multiSel && multiSelTxt) {
      if (this.selectedIds.size > 1) {
        multiSel.classList.remove('hidden');
        const selectedGuides = (this.model?.guides || []).filter(g => this.selectedIds.has(g.id));
        if (selectedGuides.length >= 2) {
          const positions = selectedGuides.map(g => g.position_pt).sort((a, b) => a - b);
          const span = positions[positions.length - 1] - positions[0];
          multiSelTxt.textContent = `${this.selectedIds.size} Lines Selected (Relative Spacing Locked: ${span.toFixed(2)} pt)`;
        } else {
          multiSelTxt.textContent = `${this.selectedIds.size} Objects Multi-Selected (Relative Offsets Locked)`;
        }
      } else {
        multiSel.classList.add('hidden');
      }
    }

    if (snapTarget) {
      if (snap.targets && snap.targets.length > 0) {
        snapTarget.textContent = `🎯 ${snap.targets[0].desc}`;
        document.getElementById('snapHud')?.classList.remove('hidden');
        document.getElementById('snapHudText').textContent = snap.targets[0].desc;
      } else {
        snapTarget.textContent = 'No Snap Target';
        document.getElementById('snapHud')?.classList.add('hidden');
      }
    }
  }

  syncColumnsFromGuides() {
    const vGuides = (this.model.guides || []).filter(g => g.orientation === 'V' && (g.owner_id === 'target_table' || g.owner_id === 'target_columns'));
    vGuides.sort((a, b) => a.position_pt - b.position_pt);

    if (vGuides.length >= 2 && this.model.columns) {
      for (let i = 0; i < Math.min(this.model.columns.length, vGuides.length - 1); i++) {
        const c = this.model.columns[i];
        c.x0_pt = vGuides[i].position_pt;
        c.x1_pt = vGuides[i+1].position_pt;
        c.width_pt = Math.max(0.1, c.x1_pt - c.x0_pt);
        c.width_mm = (c.width_pt * 25.4) / 72.0;
      }
      if (this.model.table_bbox) {
        this.model.table_bbox.x0_pt = vGuides[0].position_pt;
        this.model.table_bbox.x1_pt = vGuides[vGuides.length - 1].position_pt;
        this.model.table_bbox.width_pt = Math.max(0.1, this.model.table_bbox.x1_pt - this.model.table_bbox.x0_pt);
      }

      // Sync dimension values
      for (const col of this.model.columns) {
        const d = (this.model.dimensions || []).find(it => it.id === `dim_col_${col.column_index}_width`);
        if (d) {
          d.value_pt = col.width_pt;
          d.is_edited = true;
          d.source = 'manual';
        }
      }
      const tDim = (this.model.dimensions || []).find(it => it.id === 'dim_table_width');
      if (tDim && this.model.table_bbox) {
        tDim.value_pt = this.model.table_bbox.width_pt;
        tDim.is_edited = true;
        tDim.source = 'manual';
      }

      // Synchronize dimension lane arrows and markers in real-time
      if (this.model.dimension_lane && this.model.dimension_lane.arrows) {
        const lane = this.model.dimension_lane;
        for (let i = 0; i < Math.min(lane.arrows.length, this.model.columns.length); i++) {
          const col = this.model.columns[i];
          const arr = lane.arrows[i];
          arr.x0_pt = col.x0_pt;
          arr.x1_pt = col.x1_pt;
          arr.width_pt = col.width_pt;
          arr.label_text = `${col.width_pt.toFixed(1)} pt`;
        }
        if (lane.extension_lines) {
          vGuides.forEach((g, idx) => {
            if (lane.extension_lines[idx]) {
              lane.extension_lines[idx].x_pt = g.position_pt;
            }
          });
        }
        if (lane.numbered_markers) {
          for (let i = 0; i < Math.min(lane.numbered_markers.length, this.model.columns.length); i++) {
            const col = this.model.columns[i];
            lane.numbered_markers[i].x_pt = (col.x0_pt + col.x1_pt) / 2.0;
          }
        }
      }
    }
  }

  async copyAIPrompt() {
    try {
      const privSelect = document.getElementById('exportPrivacySelect');
      let privMode = privSelect ? privSelect.value : 'synthetic';

      if (privMode === 'real') {
        const confirmed = confirm("⚠️ CAUTION: Real customer data contains sensitive personal and financial information (PII).\n\nAre you sure you want to copy real customer data for external AI models?");
        if (!confirmed) {
          if (privSelect) privSelect.value = 'synthetic';
          privMode = 'synthetic';
          const warn = document.getElementById('exportPrivacyWarning');
          if (warn) warn.classList.add('hidden');
        }
      }

      this.showToast(`Generating Privacy-Safe AI Prompt (${privMode})...`);
      const res = await fetch(`/api/editor/${this.docId}/dimensions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          editor_model: this.model,
          format: 'ai_prompt',
          units: 'pt',
          decimals: 2,
          include_definitions: true,
          include_header: true,
          privacy_mode: privMode
        })
      });
      const data = await res.json();
      if (data.status === 'success' && data.text) {
        const toastMsg = privMode === 'real' 
          ? '⚠️ Copied AI Prompt with Real Customer Data (CAUTION: Contains PII)'
          : `🛡️ Copied AI PDF Generator Prompt (${privMode.toUpperCase()} - Safe for AI)`;
        this.copyToClipboard(data.text, toastMsg);
        const fmtSelect = document.getElementById('exportFormatSelect');
        if (fmtSelect) fmtSelect.value = 'ai_prompt';
        this.openExportModal();
      } else {
        alert("Failed to generate AI prompt: " + (data.error || "Unknown error"));
      }
    } catch (err) {
      alert("AI prompt request failed: " + err.message);
    }
  }


  copyTemplatePreset() {
    if (!this.model) return;
    const tBbox = this.model.table_bbox || {};
    const cols = (this.model.columns || []).map(c => ({
      column_index: c.column_index,
      header_text: c.header_text || '',
      width_pt: Number((c.width_pt || 0).toFixed(3)),
      x0_pt: Number((c.x0_pt || 0).toFixed(3)),
      x1_pt: Number((c.x1_pt || 0).toFixed(3)),
      alignment: c.alignment || 'left'
    }));

    const preset = {
      template_name: this.model.document_name || 'document_template',
      exported_at: new Date().toISOString(),
      page_dimensions: {
        width_pt: Number((this.model.width_pt || 612).toFixed(3)),
        height_pt: Number((this.model.height_pt || 792).toFixed(3)),
        dpi: this.model.dpi || 300
      },
      table_bbox: {
        x0_pt: Number((tBbox.x0_pt || 0).toFixed(3)),
        y0_pt: Number((tBbox.y0_pt || 0).toFixed(3)),
        x1_pt: Number((tBbox.x1_pt || 0).toFixed(3)),
        y1_pt: Number((tBbox.y1_pt || 0).toFixed(3)),
        width_pt: Number((tBbox.width_pt || 0).toFixed(3)),
        height_pt: Number((tBbox.height_pt || 0).toFixed(3))
      },
      columns: cols,
      sum_column_widths_pt: Number(cols.reduce((acc, c) => acc + c.width_pt, 0).toFixed(3)),
      guides: (this.model.guides || []).map(g => ({
        id: g.id,
        orientation: g.orientation,
        position_pt: Number((g.position_pt || 0).toFixed(3)),
        owner_id: g.owner_id
      })),
      boxes: (this.model.boxes || []).map(b => ({
        id: b.id,
        type: b.type,
        x0_pt: Number((b.x0_pt || 0).toFixed(3)),
        y0_pt: Number((b.y0_pt || 0).toFixed(3)),
        width_pt: Number((b.width_pt || 0).toFixed(3)),
        height_pt: Number((b.height_pt || 0).toFixed(3))
      }))
    };

    const presetJson = JSON.stringify(preset, null, 2);
    this.copyToClipboard(presetJson, '📋 Copied Template Dimension Preset to clipboard');
  }

  syncGeometryFromDimensions() {
    for (const d of (this.model.dimensions || [])) {
      if (d.id.startsWith('dim_col_') && d.id.endsWith('_width')) {
        const colIdx = parseInt(d.id.replace('dim_col_', '').replace('_width', ''));
        const col = (this.model.columns || []).find(c => c.column_index === colIdx);
        if (col) {
          col.width_pt = d.value_pt;
          col.width_mm = (col.width_pt * 25.4) / 72.0;
          col.x1_pt = col.x0_pt + col.width_pt;
        }
      }
    }
  }

  async snapAllColumns() {
    try {
      const res = await fetch(`/api/editor/${this.docId}/page/${this.model.page_number}/snap-columns`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ editor_model: this.model, tolerance_pt: 8.0 })
      });
      const data = await res.json();
      if (data.status === 'success' || data.editor_model) {
        this.model = data.editor_model;
        this.saveHistory();
        this.render();
        this.renderDimensionsList();
        this.renderChecksList();
        alert(`Snapped ${data.total_snapped || 0} column rules to exact real PDF rules!`);
      }
    } catch (err) {
      alert("Snap columns request failed: " + err.message);
    }
  }

  async fitTableInk() {
    try {
      const res = await fetch(`/api/editor/${this.docId}/page/${this.model.page_number}/fit-table`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ editor_model: this.model })
      });
      const data = await res.json();
      if (data.editor_model) {
        this.model = data.editor_model;
        this.saveHistory();
        this.render();
        this.renderDimensionsList();
        alert("Table bounding box expanded to outer rules and suffix ink!");
      }
    } catch (err) {
      alert("Fit table failed: " + err.message);
    }
  }

  async deduplicateGuides() {
    try {
      const res = await fetch(`/api/editor/${this.docId}/page/${this.model.page_number}/deduplicate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ guides: this.model.guides, tolerance_pt: 1.5 })
      });
      const data = await res.json();
      if (data.status === 'success') {
        this.model.guides = data.guides;
        this.saveHistory();
        this.render();
        alert(`Removed ${data.merged_count || 0} near-duplicate guides closer than 1.5 pt.`);
      }
    } catch (err) {
      alert("Deduplication request failed: " + err.message);
    }
  }

  async copyFitReport() {
    try {
      const res = await fetch(`/api/editor/${this.docId}/page/${this.model.page_number}/fit-report`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          editor_model: this.model,
          initial_auto_model: this.initialAutoModel
        })
      });
      const data = await res.json();
      if (data.status === 'success') {
        this.copyToClipboard(data.report, "Copied Auto vs Final Fit Report to clipboard");
      }
    } catch (err) {
      alert("Fit report generation failed: " + err.message);
    }
  }

  addGuide(orientation = 'V') {
    const pos = orientation === 'V' ? this.model.width_pt / 2.0 : this.model.height_pt / 2.0;
    const newId = `guide_manual_${Date.now()}`;
    this.model.guides.push({
      id: newId,
      type: 'manual_guide',
      orientation,
      position_pt: pos,
      start_pt: 0.0,
      end_pt: orientation === 'V' ? this.model.height_pt : this.model.width_pt,
      owner_id: this.activeTarget,
      stroke_width_pt: 1.0,
      source: 'manual',
      state: 'blue',
      is_edited: true,
      locked: false,
      title: `Manual ${orientation}-Rule`
    });
    this.selectedIds.clear();
    this.selectedIds.add(newId);
    this.saveHistory();
    this.render();
    this.renderDimensionsList();
  }

  deleteSelected() {
    if (this.selectedIds.size === 0) return;
    this.model.guides = (this.model.guides || []).filter(g => !this.selectedIds.has(g.id));
    this.model.boxes = (this.model.boxes || []).filter(b => !this.selectedIds.has(b.id));
    this.selectedIds.clear();
    this.saveHistory();
    this.render();
    this.renderDimensionsList();
  }

  showPropertiesPanel() {
    const empty = document.getElementById('selectionPropsEmpty');
    const content = document.getElementById('selectionPropsContent');
    if (!empty || !content) return;

    if (this.selectedIds.size === 0) {
      empty.classList.remove('hidden');
      content.classList.add('hidden');
      return;
    }

    const firstId = Array.from(this.selectedIds)[0];
    const guide = (this.model.guides || []).find(g => g.id === firstId);
    const box = (this.model.boxes || []).find(b => b.id === firstId);
    const isTable = firstId === 'target_table' || firstId === 'table' || firstId === 'table_grid' || firstId.startsWith('dim_table_');
    const isRow = firstId.startsWith('row_') || firstId.startsWith('dim_row_');
    const isCol = firstId.startsWith('col_') || firstId.startsWith('dim_col_');

    if (guide) {
      empty.classList.add('hidden');
      content.classList.remove('hidden');
      document.getElementById('propTitle').textContent = `Guide: ${guide.title || guide.id}`;
      document.getElementById('propInputTitle').value = guide.title || guide.id;
      document.getElementById('propInputX0').value = guide.orientation === 'V' ? guide.position_pt.toFixed(2) : 0;
      document.getElementById('propInputY0').value = guide.orientation === 'H' ? guide.position_pt.toFixed(2) : 0;
      document.getElementById('propBoxDimensions').classList.add('hidden');
    } else if (box) {
      empty.classList.add('hidden');
      content.classList.remove('hidden');
      document.getElementById('propTitle').textContent = `Box: ${box.title || box.id}`;
      document.getElementById('propInputTitle').value = box.title || box.id;
      document.getElementById('propInputX0').value = box.x0_pt.toFixed(2);
      document.getElementById('propInputY0').value = box.y0_pt.toFixed(2);
      document.getElementById('propBoxDimensions').classList.remove('hidden');
      document.getElementById('propInputW').value = box.width_pt.toFixed(2);
      document.getElementById('propInputH').value = box.height_pt.toFixed(2);
    } else if (isTable && this.model.table_bbox) {
      const t = this.model.table_bbox;
      empty.classList.add('hidden');
      content.classList.remove('hidden');
      document.getElementById('propTitle').textContent = `Table: Main Grid`;
      document.getElementById('propInputTitle').value = 'Table Grid';
      document.getElementById('propInputX0').value = t.x0_pt.toFixed(2);
      document.getElementById('propInputY0').value = t.y0_pt.toFixed(2);
      document.getElementById('propBoxDimensions').classList.remove('hidden');
      document.getElementById('propInputW').value = t.width_pt.toFixed(2);
      document.getElementById('propInputH').value = t.height_pt.toFixed(2);
    } else if (isRow && this.model.rows) {
      const rIdx = parseInt(firstId.replace('row_', '').replace('dim_row_', ''), 10);
      const r = (!isNaN(rIdx) && this.model.rows[rIdx]) ? this.model.rows[rIdx] : this.model.rows[0];
      if (r) {
        empty.classList.add('hidden');
        content.classList.remove('hidden');
        document.getElementById('propTitle').textContent = `Row ${rIdx || 0}`;
        document.getElementById('propInputTitle').value = `Row ${rIdx || 0}`;
        document.getElementById('propInputX0').value = (this.model.table_bbox?.x0_pt || 0).toFixed(2);
        document.getElementById('propInputY0').value = (r.y0_pt || 0).toFixed(2);
        document.getElementById('propBoxDimensions').classList.remove('hidden');
        document.getElementById('propInputW').value = (this.model.table_bbox?.width_pt || 0).toFixed(2);
        document.getElementById('propInputH').value = (r.pitch_pt || (r.y1_pt - r.y0_pt) || 0).toFixed(2);
      }
    } else if (isCol && this.model.columns) {
      const cIdx = parseInt(firstId.replace('col_', '').replace('dim_col_', '').replace('_width', ''), 10);
      const c = (!isNaN(cIdx) && this.model.columns.find(it => it.column_index === cIdx)) || this.model.columns[0];
      if (c) {
        empty.classList.add('hidden');
        content.classList.remove('hidden');
        document.getElementById('propTitle').textContent = `Column ${c.column_index}: ${c.header_text || ''}`;
        document.getElementById('propInputTitle').value = c.header_text || `Column ${c.column_index}`;
        document.getElementById('propInputX0').value = (c.x0_pt || 0).toFixed(2);
        document.getElementById('propInputY0').value = (this.model.table_bbox?.y0_pt || 0).toFixed(2);
        document.getElementById('propBoxDimensions').classList.remove('hidden');
        document.getElementById('propInputW').value = (c.width_pt || (c.x1_pt - c.x0_pt) || 0).toFixed(2);
        document.getElementById('propInputH').value = (this.model.table_bbox?.height_pt || 0).toFixed(2);
      }
    }
  }

  saveHistory() {
    this.history = this.history.slice(0, this.historyIndex + 1);
    this.history.push(JSON.parse(JSON.stringify(this.model)));
    this.historyIndex = this.history.length - 1;
  }

  undo() {
    if (this.historyIndex > 0) {
      this.historyIndex--;
      this.model = JSON.parse(JSON.stringify(this.history[this.historyIndex]));
      this.render();
      this.renderDimensionsList();
      this.renderChecksList();
    }
  }

  redo() {
    if (this.historyIndex < this.history.length - 1) {
      this.historyIndex++;
      this.model = JSON.parse(JSON.stringify(this.history[this.historyIndex]));
      this.render();
      this.renderDimensionsList();
      this.renderChecksList();
    }
  }

  formatValue(ptVal, unit = 'pt', decimals = 2) {
    let val = Number(ptVal);
    if (unit === 'mm') val = this.transform.ptToMm(val);
    else if (unit === 'px') val = this.transform.ptToPx(val);
    else if (unit === 'in') val = this.transform.ptToInches(val);
    return val.toFixed(decimals);
  }

  copyAllDimensions() {
    const lines = (this.model.dimensions || []).map(
      d => `${d.title}: ${this.formatValue(d.value_pt, this.displayUnit, this.displayDecimals)} ${this.displayUnit}`
    );
    this.copyToClipboard(lines.join('\n'), `Copied all ${lines.length} dimensions`);
  }

  openExportModal() {
    document.getElementById('exportModal')?.classList.remove('hidden');
    this.updateExportPreview();
  }

  closeExportModal() {
    document.getElementById('exportModal')?.classList.add('hidden');
  }

  async updateExportPreview() {
    const fmt = document.getElementById('exportFormatSelect')?.value || 'markdown';
    const priv = document.getElementById('exportPrivacySelect')?.value || 'synthetic';
    const unit = document.getElementById('exportUnitSelect')?.value || 'pt';
    const dec = Number(document.getElementById('exportDecimalsSelect')?.value || 2);
    const incDefs = document.getElementById('exportIncludeDefs')?.checked ?? true;

    try {
      const res = await fetch(`/api/editor/${this.docId}/dimensions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          editor_model: this.model,
          format: fmt,
          units: unit,
          decimals: dec,
          include_definitions: incDefs,
          include_header: true,
          privacy_mode: priv
        })
      });
      const data = await res.json();
      if (data.status === 'success') {
        document.getElementById('exportPreviewText').value = data.text;
      }
    } catch (err) {
      console.error("Export preview error", err);
    }
  }

  confirmCopyModal() {
    const text = document.getElementById('exportPreviewText')?.value || '';
    this.copyToClipboard(text, 'Copied formatted dimensions to clipboard');
  }

  downloadExportFile() {
    const text = document.getElementById('exportPreviewText')?.value || '';
    const fmt = document.getElementById('exportFormatSelect')?.value || 'markdown';
    const ext = fmt === 'json' ? 'json' : (fmt === 'tsv' ? 'tsv' : (fmt === 'csv' ? 'csv' : 'md'));
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `dimensions_${this.docId}.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async saveEditsToBackend() {
    try {
      const res = await fetch(`/api/editor/${this.docId}/page/${this.model.page_number}/edits`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          page_number: this.model.page_number,
          doc_id: this.docId,
          editor_model: this.model
        })
      });
      const data = await res.json();
      if (data.status === 'success') {
        this.showToast(`Saved to ${data.sidecar_file}`);
      } else {
        alert("Save failed: " + (data.error || "Unknown error"));
      }
    } catch (err) {
      alert("Save request failed: " + err.message);
    }
  }

  copyToClipboard(text, toastMsg = 'Copied to clipboard') {
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(() => this.showToast(toastMsg));
    } else {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      try {
        document.execCommand('copy');
        this.showToast(toastMsg);
      } catch (err) {
        console.error('Fallback copy error', err);
      }
      document.body.removeChild(ta);
    }
  }

  async analyzePage(pageNum) {
    try {
      this.showToast(`Analyzing Page ${pageNum}...`);
      const btn = document.getElementById('btnAnalyzeThisPage');
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin text-yellow-300"></i> <span>Analyzing...</span>`;
      }
      const res = await fetch('/api/analyze-page', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          doc_id: this.docId,
          page: pageNum,
          dpi: this.model?.dpi || 300
        })
      });
      const data = await res.json();
      if (data.status === 'success' && data.editor_model) {
        const pageImg = data.urls?.page_image || data.page_image || `/output/page_${pageNum}.png`;
        this.loadModel(data.editor_model, pageImg, this.docId);
        if (window.populateResults) {
          window.populateResults(data);
        }
        this.showToast(`Page ${pageNum} analysis complete!`);
      } else {
        alert("Page analysis failed: " + (data.error || "Unknown error"));
      }
    } catch (err) {
      alert("Error analyzing page: " + err.message);
    } finally {
      const btn = document.getElementById('btnAnalyzeThisPage');
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-bolt text-yellow-300"></i> <span>Analyze Page</span>`;
      }
    }
  }

  showToast(msg) {
    const toast = document.getElementById('copyToast');
    if (toast) {
      toast.textContent = msg;
      toast.classList.remove('opacity-0');
      setTimeout(() => toast.classList.add('opacity-0'), 2500);
    }
  }
}
