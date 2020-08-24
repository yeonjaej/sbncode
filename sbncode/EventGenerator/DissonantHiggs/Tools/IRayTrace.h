/**
 *  @file   IRayTrace.h
 *
 *  @brief  This provides an art tool interface definition for tools which can create
 *          fake particles to overlay onto input daq fragments during decoding
 *
 *  @author grayputnam@uchicago.edu
 *
 */
#ifndef IRayTrace_h
#define IRayTrace_h

// Framework Includes
#include "fhiclcpp/ParameterSet.h"
#include "art/Framework/Principal/Event.h"

// Algorithm includes
#include "TVector3.h"

#include "IHiggsStage.h"

// cpp includes
#include <vector>
#include <array>

#include "../Products/HiggsFlux.h"

//------------------------------------------------------------------------------------------------------------------------------------------

namespace evgen
{
namespace ldm {
/**
 *  @brief  IRayTrace interface class definiton
 */
class IRayTrace: virtual public IHiggsStage
{
public:
    /**
     *  @brief  Virtual Destructor
     */
    virtual ~IRayTrace() noexcept = default;

    virtual bool IntersectDetector(HiggsFlux &higgs, std::array<TVector3, 2> &intersect, double &weight) = 0;
};

} // namespace ldm
} // namespace evgen
#endif

