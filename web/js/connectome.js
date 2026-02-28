/**
 * connectome.js — Real-time "neural connectome" visualizer for Yuki
 *
 * V3 — New synthetic-life systems added:
 *  + Circadian cluster  (top-centre, amber)    — Gap 1: temporal self-awareness
 *  + DreamCycle cluster (bottom-centre, indigo) — Gap 2/8: autonomous sleep loop
 *  + UserModel cluster  (far-left, teal)        — Gap 5: user belief model
 *  + CognitiveLoad spoke on Executive          — Gap 3: somatic fatigue  
 *
 * All values come from live backend endpoints — no synthetic data.
 */

// ═══════════════════════════════════════════════════════════════════
//  COLOR HELPERS
// ═══════════════════════════════════════════════════════════════════

/** Map a 0-1 value to the three-tier palette (spec-exact). */
function valueTierColor(v) {
    if (v <= 0.3)  return '#2d3436';   // dim blue-grey
    if (v <= 0.5)  return '#00cec9';   // vibrant teal
    if (v <= 0.7)  return '#fdcb6e';   // amber
    if (v <= 0.85) return '#a29bfe';   // high-energy purple
    return '#ffffff';                   // peak white
}

/** CSS class for sidebar value spans. */
function tierClass(v) {
    if (v <= 0.3)  return 'tier-low';
    if (v <= 0.5)  return 'tier-mid';
    if (v <= 0.7)  return 'tier-mid-b';
    if (v <= 0.85) return 'tier-high';
    return 'tier-peak';
}

// ═══════════════════════════════════════════════════════════════════
//  fireSynapse  (idea #1 — link-flash transition)
//
//  Selects the synapse <line> by its DOM id, surges it bright, then
//  decays back to baseline — using two chained D3 transitions.
// ═══════════════════════════════════════════════════════════════════

/**
 * Flash a synapse: dormant → high-energy → baseline.
 * @param {string} sourceId
 * @param {string} targetId
 * @param {number} value  0..1 activation
 */
function fireSynapse(sourceId, targetId, value) {
    const colorScale = d3.interpolateRgb('#2d3436', '#a29bfe');
    // Try canonical direction first, then reversed
    const selectors = [
        `#link-${sourceId}-${targetId}`,
        `#link-${targetId}-${sourceId}`
    ];
    selectors.forEach(sel => {
        const link = d3.select(sel);
        if (link.empty()) return;
        link.interrupt()
            // Phase 1 — surge (100 ms)
            .transition('surge').duration(100).ease(d3.easeLinear)
            .attr('stroke',       colorScale(value))
            .attr('stroke-width', 2 + value * 5)   // surge thickness
            .attr('opacity',      1)
            // Phase 2 — decay (800 ms)
            .transition('decay').duration(800).ease(d3.easeCubicOut)
            .attr('stroke',       '#1e2a3a')
            .attr('stroke-width', 1.2)
            .attr('opacity',      0.5);
    });
}

// ═══════════════════════════════════════════════════════════════════
//  GRAPH SCHEMA  — nodes + links
// ═══════════════════════════════════════════════════════════════════

/*
  Cluster home positions [nx, ny] in the normalised canvas space.
  The D3 force simulation soft-anchors each node near these targets
  (via forceX / forceY) so layout is stable but physically alive.

    REACTIVE     top-left      (0.27, 0.31)
    EXECUTIVE    top-right     (0.73, 0.31)
    REFLECTIVE   bottom-right  (0.73, 0.70)
    AUTOPOIETIC  bottom-left   (0.27, 0.70)
    ENACTIVE     center        (0.50, 0.50)
    IDENTITY     inner         (0.50, 0.58)
*/

const CLUSTER_DEFS = {
    // Core cognitive quintet
    reactive:    { label: 'Reactive',    nx: 0.27, ny: 0.33, color: '#f875b0', r: 22 },
    executive:   { label: 'Executive',   nx: 0.73, ny: 0.33, color: '#55efc4', r: 22 },
    reflective:  { label: 'Reflective',  nx: 0.73, ny: 0.67, color: '#74b9ff', r: 22 },
    autopoietic: { label: 'Autopoietic', nx: 0.27, ny: 0.67, color: '#a29bfe', r: 22 },
    enactive:    { label: 'Enactive',    nx: 0.50, ny: 0.50, color: '#fff4c2', r: 32 },
    identity:    { label: 'Identity',    nx: 0.50, ny: 0.58, color: '#ffeaa7', r: 24 },
    // New synthetic-life systems
    circadian:   { label: 'Circadian',   nx: 0.50, ny: 0.11, color: '#fd9644', r: 20 },  // top-centre — time keeper
    dreamcycle:  { label: 'DreamCycle',  nx: 0.50, ny: 0.89, color: '#6c5ce7', r: 20 },  // bottom-centre — sleep loop
    usermodel:   { label: 'UserModel',   nx: 0.09, ny: 0.50, color: '#00cec9', r: 18 },  // far-left — model of user
};

/**
 * Sub-nodes orbit their parent cluster (angle in degrees, orbit in px).
 * Extended with the user's idea #3 data keys:
 *   Reactive:    sn-subconsc  ← subconscious_delta / mood_swing
 *   Executive:   sn-tokens    ← tokens_per_sec
 *   Reflective:  sn-salient-gt← salience_gate pass-rate
 *                sn-chroma    ← chroma_retrieval_score
 *   Autopoietic: sn-patdrift  ← pattern_drift
 */
const SUBNODE_DEFS = [
    // ── Reactive (valence space + subconscious delta / mood swing) ─
    { id: 'sn-valence',    cluster: 'reactive',    label: 'valence',   angle:  -90, orbit: 88,  r: 11 },
    { id: 'sn-arousal',    cluster: 'reactive',    label: 'arousal',   angle:  -20, orbit: 88,  r: 11 },
    { id: 'sn-dominance',  cluster: 'reactive',    label: 'dominance', angle: -155, orbit: 88,  r: 11 },
    { id: 'sn-joy',        cluster: 'reactive',    label: 'joy',       angle:  -50, orbit: 128, r:  9 },
    { id: 'sn-curiosity',  cluster: 'reactive',    label: 'curiosity', angle: -130, orbit: 128, r:  9 },
    { id: 'sn-subconsc',   cluster: 'reactive',    label: 'sub_delta', angle:   30, orbit: 92,  r: 10 },
    { id: 'sn-conflict',   cluster: 'reactive',    label: 'conflict',  angle:  100, orbit: 88,  r: 10 },

    // ── Executive (planning + tokens_per_sec / goal_id) ───────────
    { id: 'sn-mode',       cluster: 'executive',   label: 'response',  angle:  -90, orbit: 82,  r: 11 },
    { id: 'sn-resolution', cluster: 'executive',   label: 'resolution',angle:  -20, orbit: 82,  r: 11 },
    { id: 'sn-tokens',     cluster: 'executive',   label: 'tok/s',     angle: -155, orbit: 82,  r: 10 },
    { id: 'sn-cogload',    cluster: 'executive',   label: 'cog_load',  angle:   40, orbit: 82,  r: 10 },
    { id: 'sn-latency',    cluster: 'executive',   label: 'latency',   angle:  -55, orbit: 122, r:  9 },
    { id: 'sn-success',    cluster: 'executive',   label: 'success',   angle: -120, orbit: 122, r:  9 },

    // ── Reflective (salience_gate + chroma_retrieval_score + graph) 
    { id: 'sn-salience',   cluster: 'reflective',  label: 'salience',  angle:   90, orbit: 88,  r: 12 },
    { id: 'sn-salient-gt', cluster: 'reflective',  label: 'sal_gate',  angle:   20, orbit: 82,  r: 10 },
    { id: 'sn-chroma',     cluster: 'reflective',  label: 'chroma',    angle:  155, orbit: 82,  r: 10 },
    { id: 'sn-memories',   cluster: 'reflective',  label: 'memories',  angle:   50, orbit: 122, r:  9 },
    { id: 'sn-graph',      cluster: 'reflective',  label: 'graph',     angle:  130, orbit: 122, r:  9 },

    // ── Autopoietic (plasticity_variant + pattern_drift) ──────────
    { id: 'sn-plasticity', cluster: 'autopoietic', label: 'plasticity',angle:   90, orbit: 88,  r: 12 },
    { id: 'sn-patdrift',   cluster: 'autopoietic', label: 'pat_drift', angle:  155, orbit: 82,  r: 10 },
    { id: 'sn-cycles',     cluster: 'autopoietic', label: 'cycles',    angle:   20, orbit: 82,  r: 10 },
    { id: 'sn-goals',      cluster: 'autopoietic', label: 'goals',     angle:   55, orbit: 122, r:  9 },
    { id: 'sn-effective',  cluster: 'autopoietic', label: 'effective', angle:  125, orbit: 122, r:  9 },

    // ── Enactive (active inference + coherence core) ─────────────
    { id: 'sn-free-energy',      cluster: 'enactive', label: 'free_E',   angle:  -90, orbit: 92, r: 11 },
    { id: 'sn-pred-error',       cluster: 'enactive', label: 'pred_err',  angle:  -20, orbit: 92, r: 11 },
    { id: 'sn-model-complexity', cluster: 'enactive', label: 'complex',   angle:  150, orbit: 92, r: 10 },
    { id: 'sn-coherence',        cluster: 'enactive', label: 'coherence', angle:   60, orbit: 92, r: 10 },

    // ── Circadian (temporal priors) ───────────────────────────────
    { id: 'sn-circ-open',  cluster: 'circadian',  label: 'openness',  angle:  210, orbit: 78,  r: 10 },
    { id: 'sn-circ-rate',  cluster: 'circadian',  label: 'rate_mult', angle:  -30, orbit: 78,  r: 10 },

    // ── DreamCycle (proactive connective tissue) ──────────────────
    { id: 'sn-dc-desire',  cluster: 'dreamcycle', label: 'desire',    angle:  -90, orbit: 82,  r: 10 },
    { id: 'sn-dc-mode',    cluster: 'dreamcycle', label: 'mode',      angle:  150, orbit: 82,  r: 10 },
    { id: 'sn-dc-curious', cluster: 'dreamcycle', label: 'curious_q', angle:   30, orbit: 82,  r: 10 },

    // ── UserModel (human-model tissue) ────────────────────────────
    { id: 'sn-um-interests', cluster: 'usermodel', label: 'interests', angle:  -90, orbit: 78,  r: 9 },
    { id: 'sn-um-beliefs',   cluster: 'usermodel', label: 'beliefs',   angle:  150, orbit: 78,  r: 9 },
    { id: 'sn-um-surprise',  cluster: 'usermodel', label: 'surprise',  angle:   30, orbit: 78,  r: 9 },
];

/** Inter-cluster + cluster↔identity synapses. */
const LINK_DEFS = [
    // Enactive nexus ↔ core clusters
    { source: 'enactive',    target: 'reactive'      },
    { source: 'enactive',    target: 'executive'     },
    { source: 'enactive',    target: 'reflective'    },
    { source: 'enactive',    target: 'autopoietic'   },
    { source: 'enactive',    target: 'identity'      },
    // Cross-cluster associations
    { source: 'reactive',    target: 'executive'     },
    { source: 'executive',   target: 'reflective'    },
    { source: 'reflective',  target: 'autopoietic'   },
    { source: 'reactive',    target: 'autopoietic'   },
    { source: 'reactive',    target: 'reflective'    },
    // Circadian — time modulates all core systems
    { source: 'circadian',   target: 'reactive'      },
    { source: 'circadian',   target: 'executive'     },
    { source: 'circadian',   target: 'dreamcycle'    },
    { source: 'circadian',   target: 'enactive'      },
    // DreamCycle — feeds into reflective / nexus / identity
    { source: 'dreamcycle',  target: 'reflective'    },
    { source: 'dreamcycle',  target: 'enactive'      },
    { source: 'dreamcycle',  target: 'identity'      },
    // UserModel — user surprise feeds reactive + enactive
    { source: 'usermodel',   target: 'reactive'      },
    { source: 'usermodel',   target: 'enactive'      },
    // Reactive spokes
    { source: 'reactive',    target: 'sn-valence'    },
    { source: 'reactive',    target: 'sn-arousal'    },
    { source: 'reactive',    target: 'sn-dominance'  },
    { source: 'reactive',    target: 'sn-joy'        },
    { source: 'reactive',    target: 'sn-curiosity'  },
    { source: 'reactive',    target: 'sn-subconsc'   },
    { source: 'reactive',    target: 'sn-conflict'   },
    // Executive spokes
    { source: 'executive',   target: 'sn-mode'       },
    { source: 'executive',   target: 'sn-resolution' },
    { source: 'executive',   target: 'sn-tokens'     },
    { source: 'executive',   target: 'sn-latency'    },
    { source: 'executive',   target: 'sn-success'    },
    { source: 'executive',   target: 'sn-cogload'    },
    // Reflective spokes
    { source: 'reflective',  target: 'sn-salience'   },
    { source: 'reflective',  target: 'sn-salient-gt' },
    { source: 'reflective',  target: 'sn-chroma'     },
    { source: 'reflective',  target: 'sn-memories'   },
    { source: 'reflective',  target: 'sn-graph'      },
    // Autopoietic spokes
    { source: 'autopoietic', target: 'sn-plasticity' },
    { source: 'autopoietic', target: 'sn-patdrift'   },
    { source: 'autopoietic', target: 'sn-cycles'     },
    { source: 'autopoietic', target: 'sn-goals'      },
    { source: 'autopoietic', target: 'sn-effective'  },
    // Enactive spokes
    { source: 'enactive',    target: 'sn-free-energy'      },
    { source: 'enactive',    target: 'sn-pred-error'       },
    { source: 'enactive',    target: 'sn-model-complexity' },
    { source: 'enactive',    target: 'sn-coherence'        },
    // Circadian spokes
    { source: 'circadian',   target: 'sn-circ-open'  },
    { source: 'circadian',   target: 'sn-circ-rate'  },
    // DreamCycle spokes
    { source: 'dreamcycle',  target: 'sn-dc-desire'  },
    { source: 'dreamcycle',  target: 'sn-dc-mode'    },
    { source: 'dreamcycle',  target: 'sn-dc-curious' },
    // UserModel spokes
    { source: 'usermodel',   target: 'sn-um-interests' },
    { source: 'usermodel',   target: 'sn-um-beliefs'   },
    { source: 'usermodel',   target: 'sn-um-surprise'  },
];

// ═══════════════════════════════════════════════════════════════════
//  CONNECTOME CLASS
// ═══════════════════════════════════════════════════════════════════

class Connectome {
    constructor(svgEl, mainEl) {
        this.svg    = d3.select(svgEl);
        this.mainEl = mainEl;

        this.width  = 0;
        this.height = 0;

        // Live activation state: nodeId → 0..1
        this.activation = {};

        // Previous activation for threshold-crossing detection
        this.prevActivation = {};

        // Heartbeat state
        this.lastDataAt   = null;
        this.isDormant    = false;
        this.breathPhase  = 0;
        this.breathScale  = 1;

        // FPS tracking
        this._lastFrame   = performance.now();
        this._frameCount  = 0;
        this._fps         = 0;

        // Node / link data — arrays for D3 force sim, object for lookup
        this.nodesArr = [];
        this.linksArr = [];
        this.nodeMap  = {};

        // Keep legacy `this.nodes` alias so sidebar helpers work
        Object.defineProperty(this, 'nodes', { get: () => this.nodeMap });
        Object.defineProperty(this, 'links', { get: () => this.linksArr });

        this._buildGraph();
        this._initSVG();          // calls _resize → _drawLinks, _drawNodes
        this._buildSimulation();
        this._startLoop();
        this._subscribeToData();
    }

    // ───────────────────────────────────────────────────────────────
    //  Graph construction  (builds arrays for force sim)
    // ───────────────────────────────────────────────────────────────

    _buildGraph() {
        // Cluster nodes
        for (const [id, def] of Object.entries(CLUSTER_DEFS)) {
            const node = {
                id, label: def.label, color: def.color, r: def.r,
                nx: def.nx, ny: def.ny, isCluster: true,
                x: 0, y: 0, vx: 0, vy: 0
            };
            this.nodesArr.push(node);
            this.nodeMap[id] = node;
            this.activation[id] = 0.3;
        }

        // Sub-nodes
        for (const def of SUBNODE_DEFS) {
            const node = {
                id: def.id, label: def.label,
                color: CLUSTER_DEFS[def.cluster].color,
                r: def.r, parentId: def.cluster,
                angle: def.angle, orbit: def.orbit,
                isCluster: false,
                x: 0, y: 0, vx: 0, vy: 0
            };
            this.nodesArr.push(node);
            this.nodeMap[def.id] = node;
            this.activation[def.id] = 0.2;
        }

        // Links — store source/target IDs alongside node refs for fireSynapse
        for (const def of LINK_DEFS) {
            const s = this.nodeMap[def.source];
            const t = this.nodeMap[def.target];
            if (s && t) this.linksArr.push({
                source: s, target: t,
                sourceId: def.source, targetId: def.target
            });
        }
    }

    // ───────────────────────────────────────────────────────────────
    //  SVG initialisation
    // ───────────────────────────────────────────────────────────────

    _initSVG() {
        this.svg.selectAll('*').remove();

        // Defs: radial gradients, glow filter
        const defs = this.svg.append('defs');

        // Glow filter
        const glow = defs.append('filter')
            .attr('id', 'glow')
            .attr('x', '-50%').attr('y', '-50%')
            .attr('width', '200%').attr('height', '200%');

        glow.append('feGaussianBlur')
            .attr('in', 'SourceGraphic')
            .attr('stdDeviation', '3')
            .attr('result', 'blur');

        const feMerge = glow.append('feMerge');
        feMerge.append('feMergeNode').attr('in', 'blur');
        feMerge.append('feMergeNode').attr('in', 'SourceGraphic');

        // Desaturate filter for dormant state
        const desat = defs.append('filter').attr('id', 'desat');
        desat.append('feColorMatrix')
            .attr('type', 'saturate')
            .attr('values', '1')
            .attr('id', 'desat-matrix');

        // Strong glow for identity node
        const sg = defs.append('filter').attr('id', 'strong-glow')
            .attr('x', '-80%').attr('y', '-80%').attr('width', '260%').attr('height', '260%');
        sg.append('feGaussianBlur').attr('in', 'SourceGraphic').attr('stdDeviation', '6').attr('result', 'blur');
        const sfm = sg.append('feMerge');
        sfm.append('feMergeNode').attr('in', 'blur');
        sfm.append('feMergeNode').attr('in', 'SourceGraphic');

        // Root group (breathing transforms applied here)
        this.rootG = this.svg.append('g').attr('id', 'root-g');

        // Layers (back → front)
        this.linkLayer  = this.rootG.append('g').attr('class', 'link-layer');
        this.pulseLayer = this.rootG.append('g').attr('class', 'pulse-layer');
        this.haloLayer  = this.rootG.append('g').attr('class', 'halo-layer');
        this.nodeLayer  = this.rootG.append('g').attr('class', 'node-layer');
        this.labelLayer = this.rootG.append('g').attr('class', 'label-layer');

        this._resize();
        window.addEventListener('resize', () => this._resize());
    }

    _resize() {
        const rect  = this.mainEl.getBoundingClientRect();
        this.width  = rect.width;
        this.height = rect.height - 32;

        this.svg.attr('width', this.width).attr('height', this.height);

        // Seed initial positions so the simulation starts near target layout
        for (const n of this.nodesArr) {
            if (n.isCluster) {
                n.x = n.nx * this.width;
                n.y = n.ny * this.height;
            } else {
                const p = this.nodeMap[n.parentId];
                const rad = (n.angle * Math.PI) / 180;
                n.x = p.x + Math.cos(rad) * n.orbit;
                n.y = p.y + Math.sin(rad) * n.orbit;
            }
        }

        // Restart sim with updated canvas size
        if (this.sim) { this.sim.alpha(0.3).restart(); }

        this._drawLinks();
        this._drawNodes();
    }

    // ───────────────────────────────────────────────────────────────
    //  Force simulation  (idea #2)
    // ───────────────────────────────────────────────────────────────

    _buildSimulation() {
        const self = this;
        this.sim = d3.forceSimulation(this.nodesArr)
            // Link force: cluster–cluster links longer; spoke links shorter
            .force('link', d3.forceLink(this.linksArr).id(d => d.id)
                .distance(d => d.source.isCluster && d.target.isCluster ? 170 : 58)
                .strength(0.07))
            // Gentle repulsion
            .force('charge', d3.forceManyBody()
                .strength(d => d.isCluster ? -200 : -60))
            // Soft positional anchors — keeps clusters in their designated zones
            .force('x', d3.forceX()
                .x(d => d.isCluster
                    ? d.nx * self.width
                    : self.nodeMap[d.parentId].x + Math.cos((d.angle * Math.PI) / 180) * d.orbit)
                .strength(d => d.isCluster ? 0.18 : 0.30))
            .force('y', d3.forceY()
                .y(d => d.isCluster
                    ? d.ny * self.height
                    : self.nodeMap[d.parentId].y + Math.sin((d.angle * Math.PI) / 180) * d.orbit)
                .strength(d => d.isCluster ? 0.18 : 0.30))
            .force('collide', d3.forceCollide().radius(d => d.r + 5).strength(0.5))
            .alphaDecay(0.014)
            .velocityDecay(0.38)
            .on('tick', () => self._onSimTick());
    }

    _onSimTick() {
        this._linkSels && this._linkSels
            .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
        this._haloSels && this._haloSels
            .attr('cx', d => d.x).attr('cy', d => d.y);
        this._nodeSels && this._nodeSels
            .attr('cx', d => d.x).attr('cy', d => d.y);
        this._labelSels && this._labelSels
            .attr('x', d => d.x).attr('y', d => d.y + d.r + 13);
    }

    // ───────────────────────────────────────────────────────────────
    //  Drawing
    // ───────────────────────────────────────────────────────────────

    _drawLinks() {
        this.linkLayer.selectAll('*').remove();

        this._linkSels = this.linkLayer.selectAll('line.synapse')
            .data(this.linksArr)
            .join('line')
            .attr('class', 'synapse')
            // Unique DOM id so fireSynapse() can select by #link-srcId-tgtId
            .attr('id', d => `link-${d.sourceId}-${d.targetId}`)
            .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x).attr('y2', d => d.target.y)
            .attr('stroke', '#1e2a3a')
            .attr('stroke-width', 1.2)
            .attr('stroke-linecap', 'round')
            .attr('opacity', 0.5);
    }

    _drawNodes() {
        this.nodeLayer.selectAll('*').remove();
        this.labelLayer.selectAll('*').remove();

        const tooltip = document.getElementById('connectome-tooltip');
        const ttName  = document.getElementById('tt-name');
        const ttVal   = document.getElementById('tt-val');

        const self = this;

        const allNodes = this.nodesArr;

        // Halos (on separate layer, behind nodes)
        this._haloSels = this.haloLayer.selectAll('circle.halo')
            .data(allNodes)
            .join('circle')
            .attr('class', 'halo')
            .attr('cx', d => d.x).attr('cy', d => d.y)
            .attr('r',  d => d.r * 1.9)
            .attr('fill', d => d.color)
            .attr('opacity', 0.04)
            .attr('pointer-events', 'none');

        // Main node circles
        this._nodeSels = this.nodeLayer.selectAll('circle.node')
            .data(allNodes)
            .join('circle')
            .attr('class', 'node')
            .attr('id',   d => `node-${d.id}`)
            .attr('cx', d => d.x).attr('cy', d => d.y)
            .attr('r',  d => d.r)
            .attr('fill', '#090e1a')
            .attr('stroke', d => d.color)
            .attr('stroke-width', d => d.isCluster ? 2 : 1.5)
            // Enactive core (and identity) get a stronger glow
            .attr('filter', d => (d.id === 'enactive' || d.id === 'identity') ? 'url(#strong-glow)' : 'url(#glow)')
            .style('cursor', 'pointer')
            .on('mouseenter', function(event, d) {
                const v = self.activation[d.id] || 0;
                ttName.textContent = d.label;
                ttVal.textContent  = `activation: ${v.toFixed(3)}`;
                tooltip.style.display = 'block';
            })
            .on('mousemove', function(event) {
                const svgRect = self.mainEl.getBoundingClientRect();
                tooltip.style.left = (event.clientX - svgRect.left + 14) + 'px';
                tooltip.style.top  = (event.clientY - svgRect.top  - 10) + 'px';
            })
            .on('mouseleave', function() {
                tooltip.style.display = 'none';
            })
            .call(d3.drag()
                .on('start', function(event, d) {
                    if (!event.active) self.sim.alphaTarget(0.3).restart();
                    d.fx = d.x;
                    d.fy = d.y;
                })
                .on('drag', function(event, d) {
                    d.fx = event.x;
                    d.fy = event.y;
                })
                .on('end', function(event, d) {
                    if (!event.active) self.sim.alphaTarget(0);
                    d.fx = null;
                    d.fy = null;
                }));

        // Labels
        this._labelSels = this.labelLayer.selectAll('text.node-label')
            .data(allNodes)
            .join('text')
            .attr('class', 'node-label')
            .attr('x', d => d.x).attr('y', d => d.y + d.r + 13)
            .attr('text-anchor', 'middle')
            .attr('font-family', "'Fira Code', monospace")
            .attr('font-size', d => d.isCluster ? '11px' : '9px')
            .attr('fill', d => d.color)
            .attr('opacity', 0.72)
            .attr('pointer-events', 'none')
            .text(d => d.label);
    }

    // ───────────────────────────────────────────────────────────────
    //  Visual update (called each data refresh)
    // ───────────────────────────────────────────────────────────────

    _applyActivation() {
        const act = this.activation;

        // Update node stroke color + glow
        this._nodeSels && this._nodeSels
            .transition().duration(600).ease(d3.easeCubicOut)
            .attr('stroke', d => valueTierColor(act[d.id] || 0))
            .attr('stroke-width', d => {
                const v = act[d.id] || 0;
                return d.isCluster ? 1.5 + v * 3 : 1 + v * 2.5;
            });

        // Update halo opacity
        this._haloSels && this._haloSels
            .transition().duration(600).ease(d3.easeCubicOut)
            .attr('opacity', d => (act[d.id] || 0) * 0.18)
            .attr('r', d => d.r * (1.6 + (act[d.id] || 0) * 0.8));

        // Update synapse color based on source activation
        this._linkSels && this._linkSels
            .transition().duration(600).ease(d3.easeCubicOut)
            .attr('stroke', d => {
                const v = Math.max(act[d.source.id] || 0, act[d.target.id] || 0);
                return v > 0.5 ? d3.color(d.source.color).copy({ opacity: 0.4 }).formatRgb()
                               : '#1e2a3a';
            })
            .attr('stroke-width', d => {
                const v = Math.max(act[d.source.id] || 0, act[d.target.id] || 0);
                return 0.8 + v * 1.8;
            })
            .attr('opacity', d => {
                const v = Math.max(act[d.source.id] || 0, act[d.target.id] || 0);
                return 0.3 + v * 0.55;
            });

        // Trigger action potentials on threshold crossings
        this._checkPulses();

        // Reheat sim slightly on data arrival — keeps the graph "breathing"
        this.sim && this.sim.alpha(Math.max(this.sim.alpha(), 0.04)).restart();
    }

    // ───────────────────────────────────────────────────────────────
    //  Action potential dispatch  (ideas #1 + original traveling dot)
    // ───────────────────────────────────────────────────────────────

    _checkPulses() {
        // Rising-edge threshold — lower value catches more transitions.
        // Systems at ≥0.30 fire once when they cross the boundary from below.
        const THRESHOLD = 0.30;
        const prev = this.prevActivation;
        const curr = this.activation;

        for (const link of this.linksArr) {
            const sid  = link.sourceId;
            const tid  = link.targetId;
            const curV = curr[sid] || 0;
            const preV = prev[sid] || 0;

            // Rising-edge threshold crossing → dual animation
            if (curV >= THRESHOLD && preV < THRESHOLD) {
                fireSynapse(sid, tid, curV);   // link flash (idea #1)
                this._travelPulse(link, curV); // traveling dot (original)
            }
        }

        // ── Tonic / sustained activity ────────────────────────────────
        // Any source node with activation ≥ TONIC_THRESH fires stochastically
        // each poll tick.  This keeps existing clusters pulsing through a whole
        // chat session without waiting for a rising-edge crossing.
        // Probability rises from 10 % at baseline up to ~55 % at full activation.
        const TONIC_THRESH = 0.38;
        const sourceGroups = {};
        for (const link of this.linksArr) {
            const sid = link.sourceId;
            if (!sourceGroups[sid]) sourceGroups[sid] = [];
            sourceGroups[sid].push(link);
        }
        for (const [srcId, links] of Object.entries(sourceGroups)) {
            const actV = curr[srcId] || 0;
            if (actV < TONIC_THRESH) continue;
            const prob = 0.10 + (actV - TONIC_THRESH) * 0.73;   // 10–55 %
            if (Math.random() < prob) {
                const link = links[Math.floor(Math.random() * links.length)];
                fireSynapse(link.sourceId, link.targetId, actV);
                this._travelPulse(link, actV);
            }
        }

        // salience_gate spike → extra burst along reflective→enactive spine
        const sg  = curr['sn-salient-gt'] || 0;
        const sg0 = prev['sn-salient-gt'] || 0;
        if (sg >= 0.7 && sg0 < 0.7) {
            fireSynapse('reflective', 'enactive', sg);
            const spine = this.linksArr.find(
                l => (l.sourceId === 'reflective' && l.targetId === 'enactive') ||
                     (l.sourceId === 'enactive'   && l.targetId === 'reflective'));
            if (spine) this._travelPulse(spine, sg);
        }

        // DreamCycle high desire → lonely pulse along dreamcycle→reflective
        const dcD  = curr['sn-dc-desire'] || 0;
        const dcD0 = prev['sn-dc-desire'] || 0;
        if (dcD >= 0.75 && dcD0 < 0.75) {
            fireSynapse('dreamcycle', 'reflective', dcD);
            const dSpine = this.linksArr.find(
                l => l.sourceId === 'dreamcycle' && l.targetId === 'reflective');
            if (dSpine) this._travelPulse(dSpine, dcD);
        }

        // UserModel surprise spike → burst along usermodel→reactive
        const umS  = curr['sn-um-surprise'] || 0;
        const umS0 = prev['sn-um-surprise'] || 0;
        if (umS >= 0.55 && umS0 < 0.55) {
            fireSynapse('usermodel', 'reactive', umS);
            const uSpine = this.linksArr.find(
                l => l.sourceId === 'usermodel' && l.targetId === 'reactive');
            if (uSpine) this._travelPulse(uSpine, umS);
        }

        // Circadian band change → pulse circadian→enactive
        const circ0 = prev['circadian'] || 0;
        const circN = curr['circadian']  || 0;
        if (Math.abs(circN - circ0) > 0.15) {
            fireSynapse('circadian', 'enactive', circN);
        }
    }

    /** Animated dot that travels along a synapse from source to target. */
    _travelPulse(link, value) {
        const col      = link.source.color;
        const duration = 700 + Math.random() * 350;

        this.pulseLayer.append('circle')
            .attr('r', 3.5 + value * 3)
            .attr('cx', link.source.x).attr('cy', link.source.y)
            .attr('fill', col)
            .attr('opacity', 0.9)
            .attr('filter', 'url(#glow)')
            .transition().duration(duration).ease(d3.easeSinInOut)
            .attr('cx', link.target.x).attr('cy', link.target.y)
            .attr('opacity', 0).attr('r', 2)
            .remove();
    }

    // ───────────────────────────────────────────────────────────────
    //  Dynamic memory neuron spawning (Hebbian / chroma_retrieval)
    // ───────────────────────────────────────────────────────────────

    /**
     * Spawns a temporary memory node in the Reflective cluster.
     * If a node with the same sanitised label already exists,
     * its decay timer is reset instead of duplicating.
     *
     * @param {string} label    Human-readable label (e.g. "Fact: User likes Obsidian")
     * @param {number} salience 0..1 — controls initial size & glow
     */
    spawnMemoryNode(label, salience = 0.7) {
        const cleanLabel = String(label).slice(0, 28);
        const nodeId     = 'mem-' + cleanLabel.replace(/\W+/g, '-').toLowerCase();

        // Refresh if already exists
        if (this.nodeMap[nodeId]) {
            this.nodeMap[nodeId]._lastFired = Date.now();
            this.activation[nodeId] = Math.max(this.activation[nodeId] || 0, salience);
            this._applyActivation();
            this._showMemToast(cleanLabel);
            return;
        }

        const parent   = this.nodeMap['reflective'];
        const angle    = Math.random() * 360;
        const orbit    = 95 + Math.random() * 45;
        const rad      = (angle * Math.PI) / 180;

        const node = {
            id:        nodeId,
            label:     cleanLabel,
            color:     '#74b9ff',
            r:         7 + salience * 5,
            parentId:  'reflective',
            angle, orbit,
            isCluster: false,
            isMemNode: true,           // flag for decay sweeping
            _lastFired: Date.now(),
            x: parent.x + Math.cos(rad) * orbit,
            y: parent.y + Math.sin(rad) * orbit,
            vx: 0, vy: 0
        };

        // Integrate into simulation data
        this.nodesArr.push(node);
        this.nodeMap[nodeId] = node;
        this.activation[nodeId] = salience;

        // Link to reflective cluster
        const link = {
            source: parent, target: node,
            sourceId: 'reflective', targetId: nodeId
        };
        this.linksArr.push(link);

        // Add to simulation
        this.sim.nodes(this.nodesArr);
        this.sim.force('link').links(this.linksArr);
        this.sim.alpha(0.3).restart();

        // Redraw node/link layers with new data
        this._drawLinks();
        this._drawNodes();

        // Fade the node in from opacity 0
        d3.select(`#node-${nodeId}`)
            .attr('opacity', 0)
            .transition().duration(600).ease(d3.easeCubicOut)
            .attr('opacity', 1);

        // Fire synapse burst to announce the spawn
        fireSynapse('reflective', nodeId, salience);

        this._showMemToast(cleanLabel);
        console.info(`[Connectome] Memory neuron spawned: ${cleanLabel} (salience=${salience.toFixed(3)})`);
    }

    /**
     * Sweep memory nodes inactive for > 60 seconds and fade them out.
     * Called from the animation loop.
     */
    _tickMemoryDecay() {
        const now      = Date.now();
        const TIMEOUT  = 60_000;

        const expired = this.nodesArr.filter(
            n => n.isMemNode && (now - n._lastFired) > TIMEOUT
        );

        for (const node of expired) {
            // Fade-out transition on the circle and its label
            d3.select(`#node-${node.id}`)
                .transition().duration(2000).ease(d3.easeCubicIn)
                .attr('opacity', 0)
                .remove();

            // Remove from data structures
            this.nodesArr   = this.nodesArr.filter(n => n.id !== node.id);
            this.linksArr   = this.linksArr.filter(
                l => l.sourceId !== node.id && l.targetId !== node.id
            );
            delete this.nodeMap[node.id];
            delete this.activation[node.id];
            delete this.prevActivation[node.id];

            // Re-sync simulation
            this.sim.nodes(this.nodesArr);
            this.sim.force('link').links(this.linksArr);

            console.info(`[Connectome] Memory neuron decayed: ${node.label}`);
        }

        if (expired.length > 0) {
            this._drawLinks();
            this._drawNodes();
        }
    }

    /** Show a brief toast message when a new memory neuron spawns. */
    _showMemToast(label) {
        let toast = document.getElementById('mem-spawn-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'mem-spawn-toast';
            toast.className = 'mem-spawn-toast';
            document.getElementById('connectome-main')?.appendChild(toast);
        }
        toast.textContent = `⬡ ${label}`;
        toast.classList.add('show');
        clearTimeout(this._toastTimer);
        this._toastTimer = setTimeout(() => toast.classList.remove('show'), 3500);
    }

    // ───────────────────────────────────────────────────────────────
    //  Breathing animation (heartbeat-driven)
    // ───────────────────────────────────────────────────────────────

    _startLoop() {
        const self = this;
        let   lastDecay = 0;
        d3.timer(function(elapsed) {
            self.breathPhase = elapsed;
            self._tickBreathing();
            self._tickFPS();
            // Run memory decay check every 5 seconds
            if (elapsed - lastDecay > 5000) {
                lastDecay = elapsed;
                self._tickMemoryDecay();
            }
        });
    }

    _tickBreathing() {
        if (this.isDormant) return;

        const period  = 4000; // ms per breath cycle
        const amp     = 0.012; // ±1.2% scale
        const t       = (this.breathPhase % period) / period;
        const scale   = 1 + amp * Math.sin(t * Math.PI * 2);
        const cx      = this.width  / 2;
        const cy      = this.height / 2;

        this.rootG && this.rootG.attr(
            'transform',
            `translate(${cx*(1-scale)}, ${cy*(1-scale)}) scale(${scale})`
        );
    }

    _tickFPS() {
        this._frameCount++;
        const now = performance.now();
        if (now - this._lastFrame >= 1000) {
            this._fps = this._frameCount;
            this._frameCount = 0;
            this._lastFrame  = now;
            const el = document.getElementById('status-bar-fps');
            if (el) el.textContent = `${this._fps} fps`;
        }
    }

    // ───────────────────────────────────────────────────────────────
    //  Dormant state
    // ───────────────────────────────────────────────────────────────

    _setDormant(dormant) {
        if (this.isDormant === dormant) return;
        this.isDormant = dormant;

        const overlay  = document.getElementById('dormant-overlay');
        const hbDot    = document.getElementById('heartbeat-dot');
        const hbLabel  = document.getElementById('heartbeat-label');
        const matrix   = document.getElementById('desat-matrix');

        if (dormant) {
            overlay  && overlay.classList.add('visible');
            hbDot    && hbDot.classList.add('dormant');
            hbLabel  && (hbLabel.textContent = 'Dormant');
            matrix   && matrix.setAttribute('values', '0.08');
            this.rootG && this.rootG
                .transition().duration(1200)
                .attr('filter', 'url(#desat)');
        } else {
            overlay  && overlay.classList.remove('visible');
            hbDot    && hbDot.classList.remove('dormant');
            hbLabel  && (hbLabel.textContent = 'Heartbeat active');
            matrix   && matrix.setAttribute('values', '1');
            this.rootG && this.rootG
                .transition().duration(800)
                .attr('filter', null);
        }
    }

    // ───────────────────────────────────────────────────────────────
    //  Data subscription & mapping
    // ───────────────────────────────────────────────────────────────

    _subscribeToData() {
        const self = this;

        // ── REST polling → main graph updates ──────────────────────
        window.telemetryManager.subscribe(data => {
            self.lastDataAt = Date.now();
            self._setDormant(false);
            self._ingestData(data);
        });

        // ── WebSocket: heartbeat → global network breathing ─────────
        window.addEventListener('ws:heartbeat', () => {
            self.lastDataAt = Date.now();
            self._setDormant(false);
            // Trigger an extra breath pulse on WS heartbeat
            self._pulseBreath();
        });

        // ── WebSocket: telemetry_update → fire specific synapses ────
        window.addEventListener('ws:telemetry_update', (e) => {
            const pkt = e.detail || {};
            self.lastDataAt = Date.now();
            self._setDormant(false);

            // Prefer packet-specified source/target pair
            if (pkt.source && pkt.target) {
                const v = Number(pkt.value ?? 0);
                // Update activation for the target node if known
                if (self.nodeMap[pkt.target]) self.activation[pkt.target] = v;
                fireSynapse(pkt.source, pkt.target, v);
            }
            // If it contains a data blob, re-ingest
            if (pkt.data && window.telemetryManager.data) {
                self._ingestData(window.telemetryManager.data);
            }
        });

        // ── WebSocket: chroma_retrieval → spawn memory neuron ───────
        window.addEventListener('ws:chroma_retrieval', (e) => {
            const { label, salience } = e.detail || {};
            if (label && salience > 0.6) {
                self.spawnMemoryNode(label, salience);
            }
        });

        // ── WebSocket status → update chip in status bar ────────────
        window.addEventListener('ws:status', (e) => {
            const chip  = document.getElementById('ws-status-chip');
            if (!chip) return;
            if (e.detail.connected) {
                chip.className   = 'ws-chip connected';
                chip.textContent = '⬡ ws live';
            } else {
                chip.className   = 'ws-chip connecting';
                chip.textContent = '⬡ ws reconnecting…';
            }
        });

        // Dormancy watchdog: 20 s without data → dormant
        setInterval(() => {
            if (!self.lastDataAt) return;
            const age = Date.now() - self.lastDataAt;
            self._setDormant(age > 20000);
        }, 2000);

        // Initial parse if data is already loaded
        if (window.telemetryManager.data) {
            self._ingestData(window.telemetryManager.data);
        }
    }

    /**
     * One-shot exaggerated breath triggered on every WebSocket heartbeat.
     * Complements the continuous sinusoidal breathing in _tickBreathing().
     */
    _pulseBreath() {
        if (this.isDormant) return;
        const cx   = this.width  / 2;
        const cy   = this.height / 2;
        const peak = 1.02;  // 2% scale burst
        this.rootG
            .transition('breath-pulse').duration(200).ease(d3.easeQuadOut)
            .attr('transform',
                `translate(${cx*(1-peak)}, ${cy*(1-peak)}) scale(${peak})`)
            .transition().duration(350).ease(d3.easeQuadIn)
            .attr('transform', 'translate(0,0) scale(1)');
    }

    /**
     * Map raw telemetry to the `activation` dict and update sidebar UI.
     */
    _ingestData(data) {
        if (!data) return;

        const prev = { ...this.activation };

        const emo   = data.emotional_state        || {};
        const post  = data.postprocess_telemetry  || {};
        const mem   = data.memory_stats           || {};
        const llm   = data.llm_performance        || {};
        const auto  = data.autopoieticStatus       || {};
        const enx   = data.enactive_nexus || data.latestLog?.enactive_nexus || {};
        const kg    = data.knowledge_graph_stats  || {};
        // last_search_stats is not promoted to top-level by telemetry.js — fall back to latestLog
        const srch  = data.last_search_stats || data.latestLog?.last_search_stats || {};
        // dreamcycle_status / circadian / cognitive_load / user_model_stats are not promoted — fall back
        const dream = data.dreamcycle_status || data.latestLog?.dreamcycle_status || {};
        const temporalTrace = data.temporal_policy_trace || data.latestLog?.temporal_policy_trace || {};
        const intentionStats = data.proactive_intentions || data.latestLog?.proactive_intentions || {};

        // ── Reactive cluster ─────────────────────────────────────────
        // emotional_state uses named dimensions, not PAD — map to closest proxies:
        //   valence  ← warmth (pleasure/positivity)  │  joy as secondary
        //   arousal  ← engagement (activation level) │  intellectual_energy secondary
        //   dominance← stability (control/grounding) │  calmness secondary
        const valence   = clamp01(emo.valence   ?? emo.warmth             ?? emo.joy       ?? 0.5);
        const arousal   = clamp01(emo.arousal   ?? emo.engagement         ?? emo.intellectual_energy ?? 0.5);
        const dominance = clamp01(emo.dominance ?? emo.stability          ?? emo.calmness  ?? 0.5);
        const joy       = clamp01(emo.joy       ?? 0.5);
        const curiosity = clamp01(emo.curiosity ?? 0.5);
        const conflict  = clamp01(post.conflict_score ?? 0);

        // subconscious_delta — mean |trait delta| from post-processing
        const traitDeltas = post.trait_deltas
            ? Object.values(post.trait_deltas).map(Math.abs) : [];
        const subconsciousDelta = traitDeltas.length
            ? clamp01(mean(traitDeltas) * 4) : 0;   // 0.25 delta → 1.0
        // mood_swing — |Δvalence| between frames
        const moodSwing = clamp01(Math.abs(valence - (prev['sn-valence'] || 0)) * 5);

        this.activation['sn-valence']   = valence;
        this.activation['sn-arousal']   = arousal;
        this.activation['sn-dominance'] = dominance;
        this.activation['sn-joy']       = joy;
        this.activation['sn-curiosity'] = curiosity;
        this.activation['sn-subconsc']  = Math.max(subconsciousDelta, moodSwing);
        this.activation['sn-conflict']  = conflict;

        this.activation['reactive'] = mean([valence, arousal, dominance,
                                            joy, curiosity, subconsciousDelta, conflict]);

        // ── Executive cluster ─────────────────────────────────────────
        // response_mode is not promoted to top-level by telemetry.js — fall back to latestLog
        const _rawMode     = data.response_mode || data.latestLog?.response_mode;
        const responseMode = typeof _rawMode === 'object'
            ? (_rawMode.mode || _rawMode.tone || '')
            : (_rawMode || '');
        const responseModeScr  = modeToScore(responseMode);
        const resolutionPolicy = post.resolution_policy || 'allow';
        const resolutionScr    = policyToScore(resolutionPolicy);
        const avgLatency       = llm.avg_response_time_ms ?? 0;
        const latencyNorm      = clamp01(avgLatency / 8000);
        const llmSuccess       = clamp01(llm.success_rate ?? 1);

        // tokens_per_sec — direct key from LLM stats
        const tokensRaw  = llm.tokens_per_second ?? llm.tokens_per_sec ?? 0;
        const tokensNorm = clamp01(tokensRaw / 50);  // 50 tok/s ≈ 1.0

        // cognitive load (Gap 3) — somatic fatigue reduces executive output
        const cl      = data.cognitive_load || data.latestLog?.cognitive_load || {};
        const cogLoad = clamp01(cl.load ?? 0);

        this.activation['sn-mode']       = responseModeScr;
        this.activation['sn-resolution'] = resolutionScr;
        this.activation['sn-tokens']     = tokensNorm;
        this.activation['sn-latency']    = latencyNorm;
        this.activation['sn-success']    = llmSuccess;
        this.activation['sn-cogload']    = cogLoad;   // fatigue node

        // Tired organism = reduced executive capacity
        this.activation['executive'] = mean([responseModeScr, resolutionScr,
                                             llmSuccess, tokensNorm,
                                             clamp01(1 - latencyNorm * 0.4),
                                             clamp01(1 - cogLoad * 0.5)]);

        // ── Reflective cluster ─────────────────────────────────────────
        const salience      = clamp01(post.salience_score ?? 0);
        const memCandidates = clamp01((post.memory_candidates ?? 0) / 10);

        // salience_gate pass-rate (idea #3 key)
        const salientGate = clamp01(
            mem.salience_gate_pass_rate ??
            mem.salience_gate           ??
            (salience > 0.5 ? salience : 0));

        // chroma_retrieval_score (idea #3 key)
        const chromaScore = clamp01(
            srch.semantic_score       ??
            srch.chroma_retrieval     ??
            srch.avg_similarity_score ?? 0);

        // get_memory_stats() returns 'episodic_memories' (not total_memories / episodic_count)
        const totalMems  = mem.total_memories ?? mem.episodic_count ?? mem.episodic_memories ?? 0;
        const memoriesNorm = clamp01(totalMems / 2000);
        const graphNodes = kg.total_nodes ?? kg.nodes ?? 0;
        const graphNorm  = clamp01(graphNodes / 500);

        this.activation['sn-salience']   = salience;
        this.activation['sn-salient-gt'] = salientGate;
        this.activation['sn-chroma']     = chromaScore;
        this.activation['sn-memories']   = memoriesNorm;
        this.activation['sn-graph']      = graphNorm;

        this.activation['reflective'] = mean([salience, salientGate, chromaScore,
                                              memCandidates, memoriesNorm, graphNorm]);

        // ── Autopoietic cluster ────────────────────────────────────────
        const ap = auto.architectural_plasticity || {};
        const gf = auto.goal_formation           || {};
        const ml = auto.meta_learning            || {};

        // plasticity_variant — architectural_plasticity exposes 'average_effectiveness'
        const plasticity = clamp01(
            ap.average_effectiveness ?? ap.effectiveness_score ?? ap.adaptation_rate ?? ap.plasticity_score ?? 0);

        // pattern_drift — meta_learning summary has discovered_patterns count as proxy
        const patternDrift = clamp01(
            ml.pattern_drift    ?? ml.drift_magnitude ??
            ml.adaptation_delta ?? clamp01((ml.discovered_patterns ?? 0) / 20));

        const cyclesRaw  = auto.cycles_completed ?? 0;
        const cyclesNorm = clamp01(cyclesRaw / 200);
        const goalsRaw   = gf.active_goals ?? 0;
        const goalsNorm  = clamp01(goalsRaw / 10);
        // meta_learning summary uses 'current_effectiveness' (not 'effectiveness')
        const effectiveness = clamp01(gf.effectiveness ?? ml.current_effectiveness ?? ml.effectiveness ?? 0);

        this.activation['sn-plasticity'] = plasticity;
        this.activation['sn-patdrift']   = patternDrift;
        this.activation['sn-cycles']     = cyclesNorm;
        this.activation['sn-goals']      = goalsNorm;
        this.activation['sn-effective']  = effectiveness;

        this.activation['autopoietic'] = mean([plasticity, patternDrift,
                                               cyclesNorm, goalsNorm, effectiveness]);

        // ── Enactive nexus cluster ───────────────────────────────────
        const freeEnergy = clamp01(enx.free_energy ?? 0);
        const predictionError = clamp01(enx.prediction_error ?? 0);
        const modelComplexity = clamp01(enx.model_complexity ?? 0);
        const coherenceScore = clamp01(enx.coherence_score ?? 0);

        this.activation['sn-free-energy'] = freeEnergy;
        this.activation['sn-pred-error'] = predictionError;
        this.activation['sn-model-complexity'] = modelComplexity;
        this.activation['sn-coherence'] = coherenceScore;

        this.activation['enactive'] = mean([
            freeEnergy,
            predictionError,
            modelComplexity,
            coherenceScore,
        ]);

        // ── Identity core ──────────────────────────────────────────────
        this.activation['identity'] = mean([
            this.activation['reactive'],
            this.activation['executive'],
            this.activation['reflective'],
            this.activation['autopoietic'],
            this.activation['enactive'],
        ]);

        // ── Circadian cluster (Gap 1 — temporal self-awareness) ────────
        const circ     = data.circadian || data.latestLog?.circadian || {};
        const circOpen = clamp01(circ.openness ?? temporalTrace.openness ?? 0.5);
        const circRate = clamp01((circ.desire_rate_mult ?? temporalTrace.desire_rate_mult ?? 1.0) / 1.5);
        this.activation['sn-circ-open'] = circOpen;
        this.activation['sn-circ-rate'] = circRate;
        this.activation['circadian']    = mean([circOpen, circRate]);

        const intentPending = Number(intentionStats.pending ?? 0);
        const intentDelivered = Number(intentionStats.delivered ?? 0);
        const intentSuppressed = Number(intentionStats.suppressed ?? 0);

        // ── DreamCycle cluster (Gaps 2+8 — autonomous sleep loop) ──────
        // `dream` was already destructured at top of _ingestData — reuse it
        const dreamDesire    = clamp01(dream.desire_to_connect    ?? 0);
        const dreamActive    = dream.last_dream_mode ? 0.72 : 0.18;
        const dreamCuriosity = clamp01((dream.curiosity_queue_size ?? 0) / 8);
        this.activation['sn-dc-desire']  = dreamDesire;
        this.activation['sn-dc-mode']    = dreamActive;
        this.activation['sn-dc-curious'] = dreamCuriosity;
        this.activation['dreamcycle']    = mean([dreamDesire, dreamActive, dreamCuriosity]);

        // ── UserModel cluster (Gap 5 — model of the human) ─────────────
        const um          = data.user_model_stats || data.latestLog?.user_model_stats || {};
        const umInterests = clamp01((um.interests_count ?? 0) / 30);
        const umBeliefs   = clamp01((um.beliefs_count   ?? 0) / MAX_USER_BELIEFS);
        const umSurprise  = clamp01(um.last_surprise    ?? 0);
        this.activation['sn-um-interests'] = umInterests;
        this.activation['sn-um-beliefs']   = umBeliefs;
        this.activation['sn-um-surprise']  = umSurprise;
        this.activation['usermodel']       = clamp01(mean([umInterests, umBeliefs]) + umSurprise * 0.15);

        // ── Commit ─────────────────────────────────────────────────────
        this.prevActivation = prev;
        this._applyActivation();
        this._updateSidebar(data, {
            valence, arousal, dominance, joy, curiosity, conflict,
            subconsciousDelta, responseModeScr, resolutionScr,
            tokensRaw, tokensNorm, latencyNorm, llmSuccess, cogLoad,
            salience, salientGate, chromaScore, memCandidates,
            totalMems, graphNodes, plasticity, patternDrift,
            cyclesRaw, goalsRaw, effectiveness,
            freeEnergy, predictionError, modelComplexity, coherenceScore,
            lastPolicy: enx.last_policy || '—',
            responseMode, resolutionPolicy, avgLatency,
            // new synthetic-life fields
            circOpen, circRate,
            circBandLabel: circ.band_label || temporalTrace.band_label || '—',
            circToneHint:  circ.tone_hint  || '—',
            temporalPolicy: temporalTrace.last_policy || temporalTrace.policy || '—',
            dreamDesire, dreamActive, dreamCuriosity,
            dreamLastMode: dream.last_dream_mode  || '—',
            dreamIdleSecs: dream.idle_seconds     ?? null,
            intentPending, intentDelivered, intentSuppressed,
            umInterests, umBeliefs, umSurprise,
            umInterestsCount: um.interests_count  ?? 0,
            umBeliefsCount:   um.beliefs_count    ?? 0,
            clIsExhausted: cl.is_exhausted ?? false,
            clIsTired:     cl.is_tired     ?? false,
        });
    }

    // ───────────────────────────────────────────────────────────────
    //  Sidebar UI updates
    // ───────────────────────────────────────────────────────────────

    _updateSidebar(data, mapped) {
        const now = new Date().toLocaleTimeString();

        setVal('cm-status',       data.dreamcycle_status?.running ? 'online' : 'idle');
        setVal('cm-interactions', data.interaction_count ?? '—');
        setVal('cm-updated',      now);

        // Reactive
        setBarVal('valence',   mapped.valence);
        setBarVal('arousal',   mapped.arousal);
        setBarVal('dominance', mapped.dominance);
        setBarVal('conflict',  mapped.conflict);
        setBarVal('joy',       mapped.joy);
        setBarVal('curiosity', mapped.curiosity);

        // Executive (non-numeric)
        // last_intent is not promoted to top-level by telemetry.js — fall back to latestLog
        setNumericOrLabel('val-intent',       formatIntent(data.last_intent || data.latestLog?.last_intent));
        setNumericOrLabel('val-response-mode', formatMode(mapped.responseMode));
        setNumericOrLabel('val-resolution',    mapped.resolutionPolicy || '—');
        setNumericOrLabel('val-latency',
            mapped.avgLatency ? `${Math.round(mapped.avgLatency)} ms` : '—');

        // Reflective
        setBarVal('salience', mapped.salience);
        setVal('val-mem-candidates', data.postprocess_telemetry?.memory_candidates ?? '—');
        setVal('val-total-memories', mapped.totalMems != null && mapped.totalMems !== '' ? mapped.totalMems : '—');
        setVal('val-graph-nodes',    mapped.graphNodes || '—');

        // Autopoietic
        setBarVal('plasticity',    mapped.plasticity);
        setBarVal('effectiveness', mapped.effectiveness);
        setVal('val-cycles', mapped.cyclesRaw || '—');
        setVal('val-goals',  mapped.goalsRaw  || '—');

        // Enactive
        setBarVal('free-energy',      mapped.freeEnergy);
        setBarVal('pred-error',       mapped.predictionError);
        setBarVal('model-complexity', mapped.modelComplexity);
        setBarVal('coherence',        mapped.coherenceScore);
        setNumericOrLabel('val-enactive-policy', mapped.lastPolicy || '—');
        setNumericOrLabel('val-temporal-policy', mapped.temporalPolicy || '—');

        // Circadian (Gap 1)
        setNumericOrLabel('val-circ-band', mapped.circBandLabel || '—');
        setBarVal('circ-open', mapped.circOpen ?? 0);
        setNumericOrLabel('val-circ-tone', mapped.circToneHint  || '—');

        // DreamCycle (Gaps 2 + 8)
        setBarVal('dc-desire',  mapped.dreamDesire   ?? 0);
        setNumericOrLabel('val-dc-mode', mapped.dreamLastMode || '—');
        setVal('val-dc-curiousq', mapped.dreamCuriosity != null
            ? Math.round(mapped.dreamCuriosity * 8) : '—');
        setNumericOrLabel('val-dc-idle', mapped.dreamIdleSecs != null
            ? `${mapped.dreamIdleSecs}s` : '—');
        setVal('val-intent-pending',   mapped.intentPending ?? 0);
        setVal('val-intent-delivered', mapped.intentDelivered ?? 0);
        setVal('val-intent-suppressed', mapped.intentSuppressed ?? 0);

        // UserModel (Gap 5)
        setVal('val-um-interests', mapped.umInterestsCount ?? '—');
        setVal('val-um-beliefs',   mapped.umBeliefsCount   ?? '—');
        setBarVal('um-surprise',   mapped.umSurprise       ?? 0);

        // Cognitive Load (Gap 3) — in Executive section via sn-cogload node;
        // also surface the state label
        setBarVal('cogload', mapped.cogLoad ?? 0);
        setNumericOrLabel('val-cogload-state',
            mapped.clIsExhausted ? 'exhausted'
            : mapped.clIsTired   ? 'tired'
            : 'rested');

        // Status bar
        const sbMsg = document.getElementById('status-bar-msg');
        if (sbMsg) sbMsg.textContent = `Last update: ${now}`;

        const hbDot   = document.getElementById('heartbeat-dot');
        const hbLabel = document.getElementById('heartbeat-label');
        if (hbDot)   hbDot.classList.remove('dormant');
        if (hbLabel) hbLabel.textContent = 'Heartbeat active';
    }
}

// ═══════════════════════════════════════════════════════════════════
//  Utility helpers
// ═══════════════════════════════════════════════════════════════════

function clamp01(v) { return Math.max(0, Math.min(1, Number(v) || 0)); }
function mean(arr)  { return arr.reduce((a, b) => a + b, 0) / arr.length; }

// Cap for UserModel beliefs normalisation (matches MAX_BELIEFS in user_model.py)
const MAX_USER_BELIEFS = 30;

function modeToScore(mode) {
    if (!mode) return 0.3;
    if (typeof mode === 'object') mode = mode.mode || mode.tone || '';
    mode = String(mode).toLowerCase();
    const map = { creative: 0.85, analytical: 0.75, empathetic: 0.7,
                  reflective: 0.65, direct: 0.55, neutral: 0.45, casual: 0.4 };
    for (const [k, v] of Object.entries(map)) if (mode.includes(k)) return v;
    return 0.35;
}

function policyToScore(policy) {
    const map = { strong_rewrite: 0.9, soften: 0.6, allow: 0.25 };
    return map[policy] ?? 0.25;
}

function formatIntent(intent) {
    if (!intent) return '—';
    if (typeof intent === 'object') return intent.intent || intent.type || JSON.stringify(intent).slice(0, 20);
    return String(intent).slice(0, 18);
}

function formatMode(mode) {
    if (!mode) return '—';
    if (typeof mode === 'object') return mode.mode || mode.tone || '—';
    return String(mode).slice(0, 14);
}

/** Set text content of an element by id. */
function setVal(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val ?? '—';
}

/** Set text + tier class for a numeric sidebar label, and fill a progress bar. */
function setBarVal(key, v) {
    const span = document.getElementById(`val-${key}`);
    const fill = document.getElementById(`bar-${key}`);

    if (span) {
        span.textContent = v.toFixed(3);
        span.className   = 'csb-val ' + tierClass(v);
    }
    if (fill) {
        fill.style.width      = `${(v * 100).toFixed(1)}%`;
        fill.style.background = valueTierColor(v);
    }
}

/** Set a label-only sidebar value (non-numeric). */
function setNumericOrLabel(id, text) {
    const el = document.getElementById(id);
    if (el) { el.textContent = text || '—'; el.className = 'csb-val'; }
}

// ═══════════════════════════════════════════════════════════════════
//  Bootstrap
// ═══════════════════════════════════════════════════════════════════

(function bootstrap() {
    // Wait for DOM + D3 to be available
    function tryInit() {
        const svgEl  = document.getElementById('connectome-svg');
        const mainEl = document.getElementById('connectome-main');

        if (!svgEl || !mainEl || typeof d3 === 'undefined') {
            requestAnimationFrame(tryInit);
            return;
        }
        if (typeof window.telemetryManager === 'undefined') {
            requestAnimationFrame(tryInit);
            return;
        }

        window._connectome = new Connectome(svgEl, mainEl);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', tryInit);
    } else {
        tryInit();
    }
})();
