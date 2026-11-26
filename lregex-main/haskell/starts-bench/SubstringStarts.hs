-- Use with the haskell/src directory of Agnishom/lregex.
module SubstringStarts (startPositions) where

import Data.List (elemIndices)
import qualified Extracted as E

-- | All zero-based boundaries where a match begins, in ascending order.
-- A successful zero-width match counts, including at the end of the input.
startPositions :: E.LRegex a -> [a] -> [Int]
startPositions regex input =
    let (body, valuations) = E.absEval E.cScanMatch input regex
        -- Reversing (regex . Sigma*) puts Sigma* before the reversed body.
        search = E.rPass (E.oreverse body)
        backwardTape = E.cScanMatch search (E.orev (input, valuations))
    in elemIndices True (reverse backwardTape)
