#include "classes/DelphesClasses.h"
#include "TClonesArray.h"
#include "TFile.h"
#include "TLorentzVector.h"
#include "TSystem.h"
#include "TTree.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>

namespace {
struct RecoObject {
  int id;
  double pt;
  TLorentzVector p4;
};

bool finite(const TLorentzVector &p) {
  return std::isfinite(p.Px()) && std::isfinite(p.Py()) &&
         std::isfinite(p.Pz()) && std::isfinite(p.E()) &&
         std::isfinite(p.M());
}

void write_p4(std::ostream &out, const TLorentzVector &p) {
  out << ' ' << p.Px() << ' ' << p.Py() << ' ' << p.Pz() << ' ' << p.E()
      << ' ' << p.M();
}

void add_objects(std::vector<RecoObject> &objects, TClonesArray *branch,
                 int id) {
  for (int i = 0; i < branch->GetEntriesFast(); ++i) {
    if (id == 1) {
      auto *item = static_cast<Electron *>(branch->At(i));
      objects.push_back({id, item->PT, item->P4()});
    } else if (id == 2) {
      auto *item = static_cast<Muon *>(branch->At(i));
      objects.push_back({id, item->PT, item->P4()});
    } else {
      auto *item = static_cast<Jet *>(branch->At(i));
      objects.push_back({id, item->PT, item->P4()});
    }
  }
}

bool export_one(const std::string &channel, const std::string &input_dir,
                const std::string &output_dir) {
  const std::string input = input_dir + "/" + channel + ".root";
  const std::string output = output_dir + "/" + channel + ".dat";
  const std::string temporary = output + ".partial";
  TFile source(input.c_str());
  auto *tree = source.Get<TTree>("Delphes");
  if (!tree) {
    std::cerr << "Missing Delphes tree: " << input << '\n';
    return false;
  }

  TClonesArray *flow = nullptr, *flow_tracks = nullptr,
               *flow_photons = nullptr, *flow_neutrals = nullptr,
               *electrons = nullptr, *muons = nullptr, *jets = nullptr;
  const bool has_combined_flow = tree->GetBranch("ParticleFlowCandidate") != nullptr;
  if ((has_combined_flow &&
       tree->SetBranchAddress("ParticleFlowCandidate", &flow) < 0) ||
      (!has_combined_flow &&
       (tree->SetBranchAddress("EFlowTrack", &flow_tracks) < 0 ||
        tree->SetBranchAddress("EFlowPhoton", &flow_photons) < 0 ||
        tree->SetBranchAddress("EFlowNeutralHadron", &flow_neutrals) < 0)) ||
      tree->SetBranchAddress("Electron", &electrons) < 0 ||
      tree->SetBranchAddress("Muon", &muons) < 0 ||
      tree->SetBranchAddress("Jet", &jets) < 0) {
    std::cerr << "Missing required branch: " << input << '\n';
    return false;
  }

  std::ofstream target(temporary);
  if (!target) {
    std::cerr << "Cannot write: " << temporary << '\n';
    return false;
  }
  target << std::fixed << std::setprecision(6);
  long zero_objects = 0, over_three = 0;
  for (Long64_t event = 0; event < tree->GetEntries(); ++event) {
    if (tree->GetEntry(event) <= 0) {
      std::cerr << "Cannot read event " << event << " from " << input << '\n';
      target.close();
      std::remove(temporary.c_str());
      return false;
    }
    TLorentzVector total;
    if (has_combined_flow) {
      for (int i = 0; i < flow->GetEntriesFast(); ++i)
        total += static_cast<ParticleFlowCandidate *>(flow->At(i))->P4();
    } else {
      for (int i = 0; i < flow_tracks->GetEntriesFast(); ++i)
        total += static_cast<Track *>(flow_tracks->At(i))->P4();
      for (int i = 0; i < flow_photons->GetEntriesFast(); ++i)
        total += static_cast<Tower *>(flow_photons->At(i))->P4();
      for (int i = 0; i < flow_neutrals->GetEntriesFast(); ++i)
        total += static_cast<Tower *>(flow_neutrals->At(i))->P4();
    }

    std::vector<RecoObject> objects;
    add_objects(objects, electrons, 1);
    add_objects(objects, muons, 2);
    add_objects(objects, jets, 3);
    if (!finite(total) ||
        std::any_of(objects.begin(), objects.end(), [](const RecoObject &obj) {
          return !std::isfinite(obj.pt) || !finite(obj.p4);
        })) {
      std::cerr << "Non-finite value in " << input << " event " << event
                << '\n';
      target.close();
      std::remove(temporary.c_str());
      return false;
    }
    std::sort(objects.begin(), objects.end(),
              [](const RecoObject &a, const RecoObject &b) {
                return a.pt > b.pt;
              });
    target << event;
    write_p4(target, total);
    target << ' ' << electrons->GetEntriesFast() << ' '
           << muons->GetEntriesFast() << ' ' << jets->GetEntriesFast();
    for (int i = 0; i < 3; ++i) {
      if (i < static_cast<int>(objects.size())) {
        target << ' ' << objects[i].id;
        write_p4(target, objects[i].p4);
      } else {
        target << " 0 0 0 0 0 0";
      }
    }
    target << '\n';
    zero_objects += objects.empty();
    over_three += objects.size() > 3;
  }
  target.close();
  if (!target) {
    std::cerr << "Write failed: " << temporary << '\n';
    return false;
  }
  if (std::rename(temporary.c_str(), output.c_str()) != 0) {
    std::cerr << "Cannot finalize: " << output << '\n';
    return false;
  }
  std::cout << channel << ": events=" << tree->GetEntries()
            << " zero_objects=" << zero_objects
            << " over_three_objects=" << over_three
            << " output=" << output
            << '\n';
  return true;
}
} // namespace

void export_delphes(const char *input_dir, const char *output_dir,
                    const char *channel) {
  if (gSystem->Load("libDelphes") < 0) { gSystem->Exit(1); return; }
  gSystem->mkdir(output_dir, true);
  const std::string output = std::string(output_dir) + "/" + channel + ".dat";
  if (!gSystem->AccessPathName(output.c_str()) ||
      !gSystem->AccessPathName((output + ".partial").c_str())) {
    std::cerr << "Output already exists: " << output << '\n';
    gSystem->Exit(1); return;
  }
  if (!export_one(channel, input_dir, output_dir)) gSystem->Exit(1);
}
