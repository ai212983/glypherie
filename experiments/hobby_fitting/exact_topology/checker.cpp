// Exact filled-join reference: segment arrangement over Cartesian<Gmpq>.
//
// Reads directed straight edges as plaintext rationals from stdin, one
// per line: x1 y1 x2 y2 contour, each coordinate "num/den". Builds a
// CGAL Arrangement_2 (segment traits, exact rational kernel, so every
// intersection stays rational) and propagates per-contour windings by
// directed jumps from the unbounded face: for an atomic halfedge the
// left winding minus the right winding equals the signed count of
// covering input segments per contour. Coincident opposite segments
// cancel in the jump sum, which a regularized union would discard.
// White faces merge across zero-zero edges, so the unbounded white
// region is never a counter. Writes one JSON object to stdout;
// failures still emit {"supported":false,...} when possible.

#include <CGAL/Cartesian.h>
#include <CGAL/Gmpq.h>
#include <CGAL/Object.h>
#include <CGAL/Arr_segment_traits_2.h>
#include <CGAL/Arrangement_2.h>

#include <algorithm>
#include <functional>
#include <iostream>
#include <map>
#include <queue>
#include <set>
#include <sstream>
#include <string>
#include <vector>

typedef CGAL::Cartesian<CGAL::Gmpq> Kernel;
typedef Kernel::FT FT;
typedef Kernel::Point_2 Point_2;
typedef Kernel::Segment_2 Segment_2;
typedef CGAL::Arr_segment_traits_2<Kernel> Traits_2;
typedef CGAL::Arrangement_2<Traits_2> Arrangement_2;

namespace {

FT parse_rational(const std::string &token, bool &ok) {
    std::istringstream in(token);
    CGAL::Gmpq value;
    in >> value;
    ok = !in.fail();
    return FT(value);
}

struct InputSeg {
    Point_2 from, to;
    int contour;
};

std::string rational_string(const FT &v) {
    std::ostringstream out;
    out << v.numerator() << "/" << v.denominator();
    return out.str();
}

std::string point_string(const Point_2 &p) {
    return "[\"" + rational_string(p.x()) + "\",\"" +
           rational_string(p.y()) + "\"]";
}

}  // namespace

int main() {
    std::vector<InputSeg> inputs;
    std::string line;
    if (!std::getline(std::cin, line)) {
        std::cout << "{\"supported\":false,\"reason\":\"empty-input\"}";
        return 0;
    }
    int count = 0;
    try {
        count = std::stoi(line);
    } catch (...) {
        std::cout << "{\"supported\":false,\"reason\":\"bad-header\"}";
        return 0;
    }
    for (int i = 0; i < count; ++i) {
        if (!std::getline(std::cin, line)) {
            std::cout << "{\"supported\":false,\"reason\":\"short-input\"}";
            return 0;
        }
        std::istringstream words(line);
        std::vector<std::string> tok;
        std::string word;
        while (words >> word)
            tok.push_back(word);
        if (tok.size() != 5) {
            std::cout << "{\"supported\":false,\"reason\":\"bad-edge\"}";
            return 0;
        }
        bool ok = true;
        FT coords[4];
        for (int k = 0; k < 4; ++k) {
            coords[k] = parse_rational(tok[k], ok);
            if (!ok) {
                std::cout << "{\"supported\":false,"
                             "\"reason\":\"bad-rational\"}";
                return 0;
            }
        }
        int contour = 0;
        try {
            contour = std::stoi(tok[4]);
        } catch (...) {
            std::cout << "{\"supported\":false,\"reason\":\"bad-edge\"}";
            return 0;
        }
        Point_2 p1(coords[0], coords[1]), p2(coords[2], coords[3]);
        if (p1 == p2)
            continue;  // Python already drops exact degenerates.
        inputs.push_back({p1, p2, contour});
    }
    if (inputs.empty()) {
        std::cout << "{\"supported\":false,\"reason\":\"degenerate-input\"}";
        return 0;
    }

    Arrangement_2 arr;
    try {
        for (const InputSeg &e : inputs)
            CGAL::insert(arr, Segment_2(e.from, e.to));
    } catch (std::exception &e) {
        std::cout << "{\"supported\":false,\"reason\":\"insert-failure\"}";
        return 0;
    }

    // Face table and per-face halfedge lists. Identity uses stable
    // node pointers, never iterator-to-handle conversions.
    typedef const Arrangement_2::Face FaceNode;
    typedef const Arrangement_2::Halfedge HalfedgeNode;
    typedef const Arrangement_2::Vertex VertexNode;
    std::map<FaceNode *, int> face_index;
    std::vector<FaceNode *> faces;
    size_t unbounded = 0;
    for (auto fit = arr.faces_begin(); fit != arr.faces_end(); ++fit) {
        face_index[&*fit] = (int)faces.size();
        if (fit->is_unbounded())
            unbounded = faces.size();
        faces.push_back(&*fit);
    }
    auto face_id = [&](Arrangement_2::Face_const_handle f) {
        return face_index[&*f];
    };
    const size_t nfaces = faces.size();
    std::vector<std::vector<HalfedgeNode *> > members(nfaces);
    struct ArrEdge {
        Point_2 a, b;
        size_t f1, f2;
        int va, vb;
        std::map<int, int> cover;
    };
    std::vector<ArrEdge> arredges;
    std::map<VertexNode *, int> vertex_index;
    std::vector<VertexNode *> vertices;
    std::vector<std::vector<int> > incident;
    for (auto eit = arr.edges_begin(); eit != arr.edges_end(); ++eit) {
        HalfedgeNode *h = &*eit;
        ArrEdge edge;
        edge.a = h->source()->point();
        edge.b = h->target()->point();
        edge.f1 = face_id(h->face());
        edge.f2 = face_id(h->twin()->face());
        for (int k = 0; k < 2; ++k) {
            VertexNode *v = (k == 0) ? &*(h->source())
                                     : &*(h->target());
            auto slot = vertex_index.find(v);
            if (slot == vertex_index.end()) {
                int id = (int)vertices.size();
                vertex_index[v] = id;
                vertices.push_back(v);
                incident.push_back({});
            }
        }
        edge.va = vertex_index[&*(h->source())];
        edge.vb = vertex_index[&*(h->target())];
        // Covering input segments per contour with net direction: the
        // signed jump this atomic edge contributes across contours.
        for (const InputSeg &in : inputs) {
            FT o1 = (in.to.x() - in.from.x()) * (edge.a.y() -
                                                 in.from.y()) -
                    (in.to.y() - in.from.y()) * (edge.a.x() -
                                                 in.from.x());
            FT o2 = (in.to.x() - in.from.x()) * (edge.b.y() -
                                                 in.from.y()) -
                    (in.to.y() - in.from.y()) * (edge.b.x() -
                                                 in.from.x());
            if (o1 != 0 || o2 != 0)
                continue;
            FT lox = (edge.a.x() < edge.b.x()) ? edge.a.x()
                                               : edge.b.x();
            FT hix = (edge.a.x() < edge.b.x()) ? edge.b.x()
                                               : edge.a.x();
            FT loy = (edge.a.y() < edge.b.y()) ? edge.a.y()
                                               : edge.b.y();
            FT hiy = (edge.a.y() < edge.b.y()) ? edge.b.y()
                                               : edge.a.y();
            FT plox = (in.from.x() < in.to.x()) ? in.from.x()
                                                : in.to.x();
            FT phix = (in.from.x() < in.to.x()) ? in.to.x()
                                                : in.from.x();
            FT ploy = (in.from.y() < in.to.y()) ? in.from.y()
                                                : in.to.y();
            FT phiy = (in.from.y() < in.to.y()) ? in.to.y()
                                                : in.from.y();
            FT lo = (lox > plox) ? lox : plox;
            FT hi = (hix < phix) ? hix : phix;
            FT loy2 = (loy > ploy) ? loy : ploy;
            FT hiy2 = (hiy < phiy) ? hiy : phiy;
            if (!(hi > lo || hiy2 > loy2))
                continue;
            FT dot = (in.to.x() - in.from.x()) * (edge.b.x() -
                                                  edge.a.x()) +
                     (in.to.y() - in.from.y()) * (edge.b.y() -
                                                  edge.a.y());
            if (dot == 0)
                continue;
            edge.cover[in.contour] += (dot > 0) ? 1 : -1;
            if (edge.cover[in.contour] == 0)
                edge.cover.erase(in.contour);
        }
        int id = (int)arredges.size();
        incident[edge.va].push_back(id);
        incident[edge.vb].push_back(id);
        members[edge.f1].push_back(h);
        auto twin = h->twin();
        members[edge.f2].push_back(&*twin);
        arredges.push_back(edge);
    }

    // Contour index order for winding vectors.
    std::set<int> contour_set;
    for (const InputSeg &in : inputs)
        contour_set.insert(in.contour);
    std::vector<int> contours(contour_set.begin(), contour_set.end());
    std::map<int, int> contour_index;
    for (size_t i = 0; i < contours.size(); ++i)
        contour_index[contours[i]] = (int)i;
    const size_t ncont = contours.size();

    // Per-contour windings by directed jumps from the unbounded
    // face: W[left] = W[right] + jump along the halfedge direction.
    // The jump sums covering input segments per contour, +1 aligned
    // with the halfedge, -1 opposed; spikes cancel in the sum.
    std::vector<std::vector<int> > wind(nfaces,
                                        std::vector<int>(ncont, 0));
    std::vector<bool> known(nfaces, false);
    {
        std::queue<size_t> queue;
        queue.push(unbounded);
        known[unbounded] = true;
        while (!queue.empty()) {
            size_t cur = queue.front();
            queue.pop();
            for (HalfedgeNode *h : members[cur]) {
                size_t left = face_id(h->face());
                size_t right = face_id(h->twin()->face());
                size_t nxt;
                int sign;
                if (left == cur && !known[right]) {
                    nxt = right;
                    sign = -1;  // W[R] = W[L] - jump(h).
                } else if (right == cur && !known[left]) {
                    nxt = left;
                    sign = 1;  // W[L] = W[R] + jump(h).
                } else {
                    continue;
                }
                // Jump of h in its own direction over edge eid;
                // contours absent from the edge inherit unchanged.
                wind[nxt] = wind[cur];
                Point_2 hs = h->source()->point();
                Point_2 ht = h->target()->point();
                for (size_t eid = 0; eid < arredges.size(); ++eid) {
                    const ArrEdge &edge = arredges[eid];
                    bool fwd = (hs == edge.a && ht == edge.b);
                    bool rev = (hs == edge.b && ht == edge.a);
                    if (!fwd && !rev)
                        continue;
                    for (auto &kv : edge.cover) {
                        int net = kv.second * (fwd ? 1 : -1);
                        wind[nxt][contour_index[kv.first]] +=
                            sign * net;
                    }
                    break;
                }
                known[nxt] = true;
                queue.push(nxt);
            }
        }
    }
    for (size_t fi = 0; fi < nfaces; ++fi) {
        if (!known[fi]) {
            std::cout << "{\"supported\":false,"
                         "\"reason\":\"disconnected-face\"}";
            return 0;
        }
    }
    std::vector<int> global(nfaces, 0);
    for (size_t fi = 0; fi < nfaces; ++fi)
        for (size_t c = 0; c < ncont; ++c)
            global[fi] += wind[fi][c];

    // Filled components over any shared edge, seams included.
    std::vector<int> comp(nfaces, -1);
    int ncomp = 0;
    for (size_t fi = 0; fi < nfaces; ++fi) {
        if (global[fi] == 0 || comp[fi] >= 0)
            continue;
        std::queue<size_t> queue;
        queue.push(fi);
        comp[fi] = ncomp;
        while (!queue.empty()) {
            size_t cur = queue.front();
            queue.pop();
            for (HalfedgeNode *h : members[cur]) {
                size_t ni = face_id(h->twin()->face());
                if (global[ni] != 0 && comp[ni] < 0) {
                    comp[ni] = ncomp;
                    queue.push(ni);
                }
            }
        }
        ++ncomp;
    }

    // Exact face areas from signed halfedge shoelaces.
    std::vector<FT> area(nfaces, FT(0));
    for (size_t fi = 0; fi < nfaces; ++fi) {
        if (faces[fi]->is_unbounded())
            continue;
        FT sum(0);
        for (HalfedgeNode *h : members[fi]) {
            const Point_2 &a = h->source()->point();
            const Point_2 &b = h->target()->point();
            sum += (a.x() * b.y() - b.x() * a.y()) / FT(2);
        }
        area[fi] = (sum < 0) ? -sum : sum;
    }

    // White components merge across zero-zero edges; the region
    // holding the unbounded face is the exterior, never a counter.
    std::vector<int> white(nfaces, -1);
    int nwhite = 0;
    size_t exterior = 0;
    for (size_t fi = 0; fi < nfaces; ++fi) {
        if (global[fi] != 0 || white[fi] >= 0)
            continue;
        std::queue<size_t> queue;
        queue.push(fi);
        white[fi] = nwhite;
        if (fi == unbounded)
            exterior = (size_t)nwhite;
        while (!queue.empty()) {
            size_t cur = queue.front();
            queue.pop();
            for (HalfedgeNode *h : members[cur]) {
                size_t ni = face_id(h->twin()->face());
                if (global[ni] == 0 && white[ni] < 0) {
                    white[ni] = nwhite;
                    if (ni == unbounded)
                        exterior = (size_t)nwhite;
                    queue.push(ni);
                }
            }
        }
        ++nwhite;
    }

    // Component contour labels from boundary halfedges.
    std::vector<std::set<int> > comp_labels(ncomp);
    std::vector<int> comp_faces(ncomp, 0), comp_holes(ncomp, 0);
    std::vector<FT> comp_area(ncomp, FT(0));
    for (size_t fi = 0; fi < nfaces; ++fi) {
        if (global[fi] == 0)
            continue;
        comp_faces[comp[fi]]++;
        comp_area[comp[fi]] += area[fi];
    }
    struct SeamEdge {
        int u, v;
        std::set<int> comps;
    };
    std::vector<SeamEdge> seams;
    for (size_t eid = 0; eid < arredges.size(); ++eid) {
        const ArrEdge &edge = arredges[eid];
        bool b1 = global[edge.f1] != 0, b2 = global[edge.f2] != 0;
        if (b1 && b2) {
            SeamEdge s;
            s.u = edge.va;
            s.v = edge.vb;
            s.comps.insert(comp[edge.f1]);
            s.comps.insert(comp[edge.f2]);
            seams.push_back(s);
        }
        if (b1 != b2) {
            int c = b1 ? comp[edge.f1] : comp[edge.f2];
            for (auto &kv : edge.cover)
                comp_labels[c].insert(kv.first);
        }
    }

    // Seam chains by shared vertices (union-find, diagnostic only).
    std::vector<int> parent(vertices.size(), -1);
    for (size_t i = 0; i < vertices.size(); ++i)
        parent[i] = (int)i;
    std::function<int(int)> find = [&](int x) -> int {
        return parent[x] == x ? x : parent[x] = find(parent[x]);
    };
    for (const SeamEdge &s : seams) {
        int a = find(s.u), b = find(s.v);
        if (a != b)
            parent[a] = b;
    }
    std::map<int, std::pair<int, std::set<int> > > chains;
    for (const SeamEdge &s : seams) {
        auto &slot = chains[find(s.u)];
        slot.first++;
        slot.second.insert(s.comps.begin(), s.comps.end());
    }

    // Boundary degree and contacts per vertex from edge iteration.
    struct Contact {
        Point_2 point;
        std::set<int> comps;
        int degree;
        Contact() : point(FT(0), FT(0)), degree(0) {}
    };
    std::map<VertexNode *, Contact> touch;
    for (size_t eid = 0; eid < arredges.size(); ++eid) {
        const ArrEdge &edge = arredges[eid];
        bool b1 = global[edge.f1] != 0, b2 = global[edge.f2] != 0;
        VertexNode *ends[2] = {vertices[(size_t)edge.va],
                               vertices[(size_t)edge.vb]};
        for (int k = 0; k < 2; ++k) {
            Contact &slot = touch[ends[k]];
            slot.point = ends[k]->point();
            if (b1 != b2)
                slot.degree++;
            if (b1)
                slot.comps.insert(comp[edge.f1]);
            if (b2)
                slot.comps.insert(comp[edge.f2]);
        }
    }
    std::vector<Contact> pinches, contacts;
    for (auto &kv : touch) {
        if (kv.second.degree >= 4) {
            pinches.push_back(kv.second);
            if (kv.second.comps.size() >= 2)
                contacts.push_back(kv.second);
        }
    }
    auto by_point = [](const Contact &a, const Contact &b) {
        if (a.point.x() != b.point.x())
            return a.point.x() < b.point.x();
        if (a.point.y() != b.point.y())
            return a.point.y() < b.point.y();
        return a.degree < b.degree;
    };
    std::sort(pinches.begin(), pinches.end(), by_point);
    std::sort(contacts.begin(), contacts.end(), by_point);

    // Holes are bounded white components; adjacent boundary contours
    // come from the hole's own edges, not whole-component labels.
    struct Hole {
        FT area;
        std::set<int> adjacent;
        std::set<int> adjacent_comps;
    };
    std::vector<Hole> holes;
    std::vector<std::vector<size_t> > white_faces(nwhite);
    for (size_t fi = 0; fi < nfaces; ++fi)
        if (global[fi] == 0)
            white_faces[(size_t)white[fi]].push_back(fi);
    for (int w = 0; w < nwhite; ++w) {
        if ((size_t)w == exterior)
            continue;
        Hole hole{FT(0), {}, {}};
        for (size_t fi : white_faces[(size_t)w]) {
            hole.area += area[fi];
            for (HalfedgeNode *h : members[fi]) {
                size_t ni = face_id(h->twin()->face());
                if (global[ni] == 0)
                    continue;
                hole.adjacent_comps.insert(comp[ni]);
                size_t eid = 0;
                for (; eid < arredges.size(); ++eid) {
                    const ArrEdge &edge = arredges[eid];
                    bool match = (edge.f1 == fi && edge.f2 == ni) ||
                                 (edge.f1 == ni && edge.f2 == fi);
                    if (!match)
                        continue;
                    for (auto &kv : edge.cover)
                        hole.adjacent.insert(kv.first);
                    break;
                }
            }
        }
        holes.push_back(hole);
        for (int c : hole.adjacent_comps)
            comp_holes[c]++;
    }

    // Per-pair attachment classes. Masks use individual contour
    // windings, so coincident cancellations still expose sharing.
    struct PairRec {
        int first, second;
        int area_components, area_holes;
        int edge_components, point_contacts;
        std::vector<int> boundary_degrees;
    };
    std::vector<PairRec> pairs;
    std::vector<std::vector<int> > mask_index(
        nfaces, std::vector<int>(ncont, 0));
    for (size_t fi = 0; fi < nfaces; ++fi)
        for (size_t c = 0; c < ncont; ++c)
            mask_index[fi][c] = (wind[fi][c] != 0) ? 1 : 0;
    for (size_t a = 0; a < ncont; ++a) {
        for (size_t b = a + 1; b < ncont; ++b) {
            auto in_mask = [&](size_t fi) {
                return mask_index[fi][a] && mask_index[fi][b];
            };
            int area_components = 0;
            {
                std::vector<bool> seen(nfaces, false);
                for (size_t fi = 0; fi < nfaces; ++fi) {
                    if (!in_mask(fi) || seen[fi])
                        continue;
                    area_components++;
                    std::queue<size_t> queue;
                    queue.push(fi);
                    seen[fi] = true;
                    while (!queue.empty()) {
                        size_t cur = queue.front();
                        queue.pop();
                        for (HalfedgeNode *h : members[cur]) {
                            size_t ni = face_id(h->twin()->face());
                            if (in_mask(ni) && !seen[ni]) {
                                seen[ni] = true;
                                queue.push(ni);
                            }
                        }
                    }
                }
            }
            int area_holes = 0;
            {
                std::vector<int> wmask(nfaces, -1);
                int nw = 0;
                for (size_t fi = 0; fi < nfaces; ++fi) {
                    if (in_mask(fi) || wmask[fi] >= 0)
                        continue;
                    std::queue<size_t> queue;
                    queue.push(fi);
                    wmask[fi] = nw;
                    bool touches_unbounded = (fi == unbounded);
                    while (!queue.empty()) {
                        size_t cur = queue.front();
                        queue.pop();
                        for (HalfedgeNode *h : members[cur]) {
                            size_t ni = face_id(h->twin()->face());
                            if (!in_mask(ni) && wmask[ni] < 0) {
                                wmask[ni] = nw;
                                if (ni == unbounded)
                                    touches_unbounded = true;
                                queue.push(ni);
                            }
                        }
                    }
                    if (!touches_unbounded)
                        area_holes++;
                    ++nw;
                }
            }
            // Pure edge contacts: both contours cover the edge but
            // no incident face carries the intersection mask.
            std::vector<int> edge_contact(arredges.size(), 0);
            for (size_t eid = 0; eid < arredges.size(); ++eid) {
                const ArrEdge &edge = arredges[eid];
                bool covers_a = false, covers_b = false;
                for (auto &kv : edge.cover) {
                    if (kv.first == contours[a])
                        covers_a = true;
                    if (kv.first == contours[b])
                        covers_b = true;
                }
                if (!covers_a || !covers_b)
                    continue;
                if (in_mask(edge.f1) || in_mask(edge.f2))
                    continue;
                edge_contact[eid] = 1;
            }
            int edge_components = 0;
            {
                std::vector<int> parent2(vertices.size(), -1);
                for (size_t i = 0; i < vertices.size(); ++i)
                    parent2[i] = (int)i;
                std::function<int(int)> find2 = [&](int x) -> int {
                    return parent2[x] == x ? x
                                           : parent2[x] = find2(parent2[x]);
                };
                for (size_t eid = 0; eid < arredges.size(); ++eid) {
                    if (!edge_contact[eid])
                        continue;
                    int u = find2(arredges[eid].va);
                    int v = find2(arredges[eid].vb);
                    if (u != v)
                        parent2[u] = v;
                }
                std::set<int> roots;
                for (size_t eid = 0; eid < arredges.size(); ++eid)
                    if (edge_contact[eid])
                        roots.insert(find2(arredges[eid].va));
                edge_components = (int)roots.size();
            }
            int point_contacts = 0;
            for (size_t vi = 0; vi < vertices.size(); ++vi) {
                bool covers_a = false, covers_b = false;
                bool mask_near = false, edge_near = false;
                for (int eid : incident[vi]) {
                    for (auto &kv : arredges[(size_t)eid].cover) {
                        if (kv.first == contours[a])
                            covers_a = true;
                        if (kv.first == contours[b])
                            covers_b = true;
                    }
                    if (edge_contact[(size_t)eid])
                        edge_near = true;
                    if (in_mask(arredges[(size_t)eid].f1) ||
                        in_mask(arredges[(size_t)eid].f2))
                        mask_near = true;
                }
                if (covers_a && covers_b && !mask_near && !edge_near)
                    point_contacts++;
            }
            // Intersection-mask boundary singularities: incident
            // arrangement edges separating mask interior from
            // exterior. Manifold boundary vertices have degree 2;
            // any other positive degree is a pinch or branch of
            // the shared boundary, invisible to area/edge/point
            // counts when a covering contour hides it globally.
            std::vector<int> boundary_degrees;
            for (size_t vi = 0; vi < vertices.size(); ++vi) {
                int deg = 0;
                for (int eid : incident[vi]) {
                    if (in_mask(arredges[(size_t)eid].f1) !=
                        in_mask(arredges[(size_t)eid].f2))
                        deg++;
                }
                if (deg > 0 && deg != 2)
                    boundary_degrees.push_back(deg);
            }
            std::sort(boundary_degrees.begin(),
                      boundary_degrees.end());
            if (area_components > 0 || area_holes > 0 ||
                edge_components > 0 || point_contacts > 0 ||
                !boundary_degrees.empty()) {
                PairRec rec = {contours[a], contours[b],
                               area_components, area_holes,
                               edge_components, point_contacts,
                               boundary_degrees};
                pairs.push_back(rec);
            }
        }
    }

    FT total(0);
    for (int c = 0; c < ncomp; ++c)
        total += comp_area[c];

    auto print_label_set = [](const std::set<int> &comps,
                              const std::vector<std::set<int> > &labels) {
        std::cout << "[";
        bool first = true;
        for (int c : comps) {
            if (!first)
                std::cout << ",";
            std::cout << "[";
            bool inner = true;
            for (int label : labels[c]) {
                if (!inner)
                    std::cout << ",";
                std::cout << label;
                inner = false;
            }
            std::cout << "]";
            first = false;
        }
        std::cout << "]";
    };
    std::cout << "{\"supported\":true,";
    std::cout << "\"total_filled_area\":\"" << rational_string(total)
              << "\",";
    std::cout << "\"components\":[";
    for (int c = 0; c < ncomp; ++c) {
        if (c)
            std::cout << ",";
        std::cout << "{\"id\":" << c << ",\"area\":\""
                  << rational_string(comp_area[c]) << "\",\"faces\":"
                  << comp_faces[c] << ",\"holes\":" << comp_holes[c]
                  << ",\"contours\":[";
        bool first = true;
        for (int label : comp_labels[c]) {
            if (!first)
                std::cout << ",";
            std::cout << label;
            first = false;
        }
        std::cout << "]}";
    }
    std::cout << "],\"holes\":[";
    for (size_t i = 0; i < holes.size(); ++i) {
        if (i)
            std::cout << ",";
        std::cout << "{\"area\":\"" << rational_string(holes[i].area)
                  << "\",\"adjacent\":[";
        bool first = true;
        for (int label : holes[i].adjacent) {
            if (!first)
                std::cout << ",";
            std::cout << label;
            first = false;
        }
        std::cout << "]}";
    }
    std::cout << "],\"seam_chains\":[";
    bool first_chain = true;
    for (auto &kv : chains) {
        if (!first_chain)
            std::cout << ",";
        std::cout << "{\"edges\":" << kv.second.first
                  << ",\"components\":";
        print_label_set(kv.second.second, comp_labels);
        std::cout << "}";
        first_chain = false;
    }
    std::cout << "],\"pinch_vertices\":[";
    for (size_t i = 0; i < pinches.size(); ++i) {
        if (i)
            std::cout << ",";
        std::cout << "{\"point\":" << point_string(pinches[i].point)
                  << ",\"degree\":" << pinches[i].degree
                  << ",\"components\":";
        print_label_set(pinches[i].comps, comp_labels);
        std::cout << "}";
    }
    std::cout << "],\"point_contacts\":[";
    for (size_t i = 0; i < contacts.size(); ++i) {
        if (i)
            std::cout << ",";
        std::cout << "{\"point\":" << point_string(contacts[i].point)
                  << ",\"sides\":";
        print_label_set(contacts[i].comps, comp_labels);
        std::cout << "}";
    }
    std::cout << "],\"pairs\":[";
    for (size_t i = 0; i < pairs.size(); ++i) {
        if (i)
            std::cout << ",";
        std::cout << "{\"pair\":[" << pairs[i].first << ","
                  << pairs[i].second << "],\"area_components\":"
                  << pairs[i].area_components << ",\"area_holes\":"
                  << pairs[i].area_holes << ",\"edge_components\":"
                  << pairs[i].edge_components << ",\"point_contacts\":"
                  << pairs[i].point_contacts << ",\"boundary_degrees\":[";
        for (size_t j = 0; j < pairs[i].boundary_degrees.size(); ++j) {
            if (j)
                std::cout << ",";
            std::cout << pairs[i].boundary_degrees[j];
        }
        std::cout << "]}";
    }
    std::cout << "]}";
    return 0;
}
