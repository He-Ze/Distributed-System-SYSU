/**
* @file protoBitmask.cpp
* 
* @brief This class also provides space-efficient binary storage 
*/

#include "protoBitmask.h"
#include "protoDebug.h"
/** 
 * @file protoBitmask.cpp
 *
 * @brief This class provides space-efficient binary storage.
 */

// Hamming weights for given one-byte bit masks
const unsigned char ProtoBitmask::WEIGHT[256] = 
{
    0, 1, 1, 2, 1, 2, 2, 3, 1, 2, 2, 3, 2, 3, 3, 4, 
    1, 2, 2, 3, 2, 3, 3, 4, 2, 3, 3, 4, 3, 4, 4, 5, 
    1, 2, 2, 3, 2, 3, 3, 4, 2, 3, 3, 4, 3, 4, 4, 5, 
    2, 3, 3, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 5, 5, 6, 
    1, 2, 2, 3, 2, 3, 3, 4, 2, 3, 3, 4, 3, 4, 4, 5, 
    2, 3, 3, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 5, 5, 6, 
    2, 3, 3, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 5, 5, 6, 
    3, 4, 4, 5, 4, 5, 5, 6, 4, 5, 5, 6, 5, 6, 6, 7, 
    1, 2, 2, 3, 2, 3, 3, 4, 2, 3, 3, 4, 3, 4, 4, 5, 
    2, 3, 3, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 5, 5, 6, 
    2, 3, 3, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 5, 5, 6, 
    3, 4, 4, 5, 4, 5, 5, 6, 4, 5, 5, 6, 5, 6, 6, 7, 
    2, 3, 3, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 5, 5, 6, 
    3, 4, 4, 5, 4, 5, 5, 6, 4, 5, 5, 6, 5, 6, 6, 7, 
    3, 4, 4, 5, 4, 5, 5, 6, 4, 5, 5, 6, 5, 6, 6, 7, 
    4, 5, 5, 6, 5, 6, 6, 7, 5, 6, 6, 7, 6, 7, 7, 8
};

// Bit location vectors for given one-byte bit masks
const unsigned char ProtoBitmask::BITLOCS[256][8] = 
{
    {0, 0, 0, 0, 0, 0, 0, 0}, {7, 0, 0, 0, 0, 0, 0, 0}, 
    {6, 0, 0, 0, 0, 0, 0, 0}, {6, 7, 0, 0, 0, 0, 0, 0}, 
    {5, 0, 0, 0, 0, 0, 0, 0}, {5, 7, 0, 0, 0, 0, 0, 0}, 
    {5, 6, 0, 0, 0, 0, 0, 0}, {5, 6, 7, 0, 0, 0, 0, 0}, 
    {4, 0, 0, 0, 0, 0, 0, 0}, {4, 7, 0, 0, 0, 0, 0, 0}, 
    {4, 6, 0, 0, 0, 0, 0, 0}, {4, 6, 7, 0, 0, 0, 0, 0}, 
    {4, 5, 0, 0, 0, 0, 0, 0}, {4, 5, 7, 0, 0, 0, 0, 0}, 
    {4, 5, 6, 0, 0, 0, 0, 0}, {4, 5, 6, 7, 0, 0, 0, 0}, 
    {3, 0, 0, 0, 0, 0, 0, 0}, {3, 7, 0, 0, 0, 0, 0, 0}, 
    {3, 6, 0, 0, 0, 0, 0, 0}, {3, 6, 7, 0, 0, 0, 0, 0}, 
    {3, 5, 0, 0, 0, 0, 0, 0}, {3, 5, 7, 0, 0, 0, 0, 0}, 
    {3, 5, 6, 0, 0, 0, 0, 0}, {3, 5, 6, 7, 0, 0, 0, 0}, 
    {3, 4, 0, 0, 0, 0, 0, 0}, {3, 4, 7, 0, 0, 0, 0, 0}, 
    {3, 4, 6, 0, 0, 0, 0, 0}, {3, 4, 6, 7, 0, 0, 0, 0}, 
    {3, 4, 5, 0, 0, 0, 0, 0}, {3, 4, 5, 7, 0, 0, 0, 0}, 
    {3, 4, 5, 6, 0, 0, 0, 0}, {3, 4, 5, 6, 7, 0, 0, 0}, 
    {2, 0, 0, 0, 0, 0, 0, 0}, {2, 7, 0, 0, 0, 0, 0, 0}, 
    {2, 6, 0, 0, 0, 0, 0, 0}, {2, 6, 7, 0, 0, 0, 0, 0}, 
    {2, 5, 0, 0, 0, 0, 0, 0}, {2, 5, 7, 0, 0, 0, 0, 0}, 
    {2, 5, 6, 0, 0, 0, 0, 0}, {2, 5, 6, 7, 0, 0, 0, 0}, 
    {2, 4, 0, 0, 0, 0, 0, 0}, {2, 4, 7, 0, 0, 0, 0, 0}, 
    {2, 4, 6, 0, 0, 0, 0, 0}, {2, 4, 6, 7, 0, 0, 0, 0}, 
    {2, 4, 5, 0, 0, 0, 0, 0}, {2, 4, 5, 7, 0, 0, 0, 0}, 
    {2, 4, 5, 6, 0, 0, 0, 0}, {2, 4, 5, 6, 7, 0, 0, 0}, 
    {2, 3, 0, 0, 0, 0, 0, 0}, {2, 3, 7, 0, 0, 0, 0, 0}, 
    {2, 3, 6, 0, 0, 0, 0, 0}, {2, 3, 6, 7, 0, 0, 0, 0}, 
    {2, 3, 5, 0, 0, 0, 0, 0}, {2, 3, 5, 7, 0, 0, 0, 0}, 
    {2, 3, 5, 6, 0, 0, 0, 0}, {2, 3, 5, 6, 7, 0, 0, 0}, 
    {2, 3, 4, 0, 0, 0, 0, 0}, {2, 3, 4, 7, 0, 0, 0, 0}, 
    {2, 3, 4, 6, 0, 0, 0, 0}, {2, 3, 4, 6, 7, 0, 0, 0}, 
    {2, 3, 4, 5, 0, 0, 0, 0}, {2, 3, 4, 5, 7, 0, 0, 0}, 
    {2, 3, 4, 5, 6, 0, 0, 0}, {2, 3, 4, 5, 6, 7, 0, 0}, 
    {1, 0, 0, 0, 0, 0, 0, 0}, {1, 7, 0, 0, 0, 0, 0, 0}, 
    {1, 6, 0, 0, 0, 0, 0, 0}, {1, 6, 7, 0, 0, 0, 0, 0}, 
    {1, 5, 0, 0, 0, 0, 0, 0}, {1, 5, 7, 0, 0, 0, 0, 0}, 
    {1, 5, 6, 0, 0, 0, 0, 0}, {1, 5, 6, 7, 0, 0, 0, 0}, 
    {1, 4, 0, 0, 0, 0, 0, 0}, {1, 4, 7, 0, 0, 0, 0, 0}, 
    {1, 4, 6, 0, 0, 0, 0, 0}, {1, 4, 6, 7, 0, 0, 0, 0}, 
    {1, 4, 5, 0, 0, 0, 0, 0}, {1, 4, 5, 7, 0, 0, 0, 0}, 
    {1, 4, 5, 6, 0, 0, 0, 0}, {1, 4, 5, 6, 7, 0, 0, 0}, 
    {1, 3, 0, 0, 0, 0, 0, 0}, {1, 3, 7, 0, 0, 0, 0, 0}, 
    {1, 3, 6, 0, 0, 0, 0, 0}, {1, 3, 6, 7, 0, 0, 0, 0}, 
    {1, 3, 5, 0, 0, 0, 0, 0}, {1, 3, 5, 7, 0, 0, 0, 0}, 
    {1, 3, 5, 6, 0, 0, 0, 0}, {1, 3, 5, 6, 7, 0, 0, 0}, 
    {1, 3, 4, 0, 0, 0, 0, 0}, {1, 3, 4, 7, 0, 0, 0, 0}, 
    {1, 3, 4, 6, 0, 0, 0, 0}, {1, 3, 4, 6, 7, 0, 0, 0}, 
    {1, 3, 4, 5, 0, 0, 0, 0}, {1, 3, 4, 5, 7, 0, 0, 0}, 
    {1, 3, 4, 5, 6, 0, 0, 0}, {1, 3, 4, 5, 6, 7, 0, 0}, 
    {1, 2, 0, 0, 0, 0, 0, 0}, {1, 2, 7, 0, 0, 0, 0, 0}, 
    {1, 2, 6, 0, 0, 0, 0, 0}, {1, 2, 6, 7, 0, 0, 0, 0}, 
    {1, 2, 5, 0, 0, 0, 0, 0}, {1, 2, 5, 7, 0, 0, 0, 0}, 
    {1, 2, 5, 6, 0, 0, 0, 0}, {1, 2, 5, 6, 7, 0, 0, 0}, 
    {1, 2, 4, 0, 0, 0, 0, 0}, {1, 2, 4, 7, 0, 0, 0, 0}, 
    {1, 2, 4, 6, 0, 0, 0, 0}, {1, 2, 4, 6, 7, 0, 0, 0}, 
    {1, 2, 4, 5, 0, 0, 0, 0}, {1, 2, 4, 5, 7, 0, 0, 0}, 
    {1, 2, 4, 5, 6, 0, 0, 0}, {1, 2, 4, 5, 6, 7, 0, 0}, 
    {1, 2, 3, 0, 0, 0, 0, 0}, {1, 2, 3, 7, 0, 0, 0, 0}, 
    {1, 2, 3, 6, 0, 0, 0, 0}, {1, 2, 3, 6, 7, 0, 0, 0}, 
    {1, 2, 3, 5, 0, 0, 0, 0}, {1, 2, 3, 5, 7, 0, 0, 0}, 
    {1, 2, 3, 5, 6, 0, 0, 0}, {1, 2, 3, 5, 6, 7, 0, 0}, 
    {1, 2, 3, 4, 0, 0, 0, 0}, {1, 2, 3, 4, 7, 0, 0, 0}, 
    {1, 2, 3, 4, 6, 0, 0, 0}, {1, 2, 3, 4, 6, 7, 0, 0}, 
    {1, 2, 3, 4, 5, 0, 0, 0}, {1, 2, 3, 4, 5, 7, 0, 0}, 
    {1, 2, 3, 4, 5, 6, 0, 0}, {1, 2, 3, 4, 5, 6, 7, 0}, 
    {0, 0, 0, 0, 0, 0, 0, 0}, {0, 7, 0, 0, 0, 0, 0, 0}, 
    {0, 6, 0, 0, 0, 0, 0, 0}, {0, 6, 7, 0, 0, 0, 0, 0}, 
    {0, 5, 0, 0, 0, 0, 0, 0}, {0, 5, 7, 0, 0, 0, 0, 0}, 
    {0, 5, 6, 0, 0, 0, 0, 0}, {0, 5, 6, 7, 0, 0, 0, 0}, 
    {0, 4, 0, 0, 0, 0, 0, 0}, {0, 4, 7, 0, 0, 0, 0, 0}, 
    {0, 4, 6, 0, 0, 0, 0, 0}, {0, 4, 6, 7, 0, 0, 0, 0}, 
    {0, 4, 5, 0, 0, 0, 0, 0}, {0, 4, 5, 7, 0, 0, 0, 0}, 
    {0, 4, 5, 6, 0, 0, 0, 0}, {0, 4, 5, 6, 7, 0, 0, 0}, 
    {0, 3, 0, 0, 0, 0, 0, 0}, {0, 3, 7, 0, 0, 0, 0, 0}, 
    {0, 3, 6, 0, 0, 0, 0, 0}, {0, 3, 6, 7, 0, 0, 0, 0}, 
    {0, 3, 5, 0, 0, 0, 0, 0}, {0, 3, 5, 7, 0, 0, 0, 0}, 
    {0, 3, 5, 6, 0, 0, 0, 0}, {0, 3, 5, 6, 7, 0, 0, 0}, 
    {0, 3, 4, 0, 0, 0, 0, 0}, {0, 3, 4, 7, 0, 0, 0, 0}, 
    {0, 3, 4, 6, 0, 0, 0, 0}, {0, 3, 4, 6, 7, 0, 0, 0}, 
    {0, 3, 4, 5, 0, 0, 0, 0}, {0, 3, 4, 5, 7, 0, 0, 0}, 
    {0, 3, 4, 5, 6, 0, 0, 0}, {0, 3, 4, 5, 6, 7, 0, 0}, 
    {0, 2, 0, 0, 0, 0, 0, 0}, {0, 2, 7, 0, 0, 0, 0, 0}, 
    {0, 2, 6, 0, 0, 0, 0, 0}, {0, 2, 6, 7, 0, 0, 0, 0}, 
    {0, 2, 5, 0, 0, 0, 0, 0}, {0, 2, 5, 7, 0, 0, 0, 0}, 
    {0, 2, 5, 6, 0, 0, 0, 0}, {0, 2, 5, 6, 7, 0, 0, 0}, 
    {0, 2, 4, 0, 0, 0, 0, 0}, {0, 2, 4, 7, 0, 0, 0, 0}, 
    {0, 2, 4, 6, 0, 0, 0, 0}, {0, 2, 4, 6, 7, 0, 0, 0}, 
    {0, 2, 4, 5, 0, 0, 0, 0}, {0, 2, 4, 5, 7, 0, 0, 0}, 
    {0, 2, 4, 5, 6, 0, 0, 0}, {0, 2, 4, 5, 6, 7, 0, 0}, 
    {0, 2, 3, 0, 0, 0, 0, 0}, {0, 2, 3, 7, 0, 0, 0, 0}, 
    {0, 2, 3, 6, 0, 0, 0, 0}, {0, 2, 3, 6, 7, 0, 0, 0}, 
    {0, 2, 3, 5, 0, 0, 0, 0}, {0, 2, 3, 5, 7, 0, 0, 0}, 
    {0, 2, 3, 5, 6, 0, 0, 0}, {0, 2, 3, 5, 6, 7, 0, 0}, 
    {0, 2, 3, 4, 0, 0, 0, 0}, {0, 2, 3, 4, 7, 0, 0, 0}, 
    {0, 2, 3, 4, 6, 0, 0, 0}, {0, 2, 3, 4, 6, 7, 0, 0}, 
    {0, 2, 3, 4, 5, 0, 0, 0}, {0, 2, 3, 4, 5, 7, 0, 0}, 
    {0, 2, 3, 4, 5, 6, 0, 0}, {0, 2, 3, 4, 5, 6, 7, 0}, 
    {0, 1, 0, 0, 0, 0, 0, 0}, {0, 1, 7, 0, 0, 0, 0, 0}, 
    {0, 1, 6, 0, 0, 0, 0, 0}, {0, 1, 6, 7, 0, 0, 0, 0}, 
    {0, 1, 5, 0, 0, 0, 0, 0}, {0, 1, 5, 7, 0, 0, 0, 0}, 
    {0, 1, 5, 6, 0, 0, 0, 0}, {0, 1, 5, 6, 7, 0, 0, 0}, 
    {0, 1, 4, 0, 0, 0, 0, 0}, {0, 1, 4, 7, 0, 0, 0, 0}, 
    {0, 1, 4, 6, 0, 0, 0, 0}, {0, 1, 4, 6, 7, 0, 0, 0}, 
    {0, 1, 4, 5, 0, 0, 0, 0}, {0, 1, 4, 5, 7, 0, 0, 0}, 
    {0, 1, 4, 5, 6, 0, 0, 0}, {0, 1, 4, 5, 6, 7, 0, 0}, 
    {0, 1, 3, 0, 0, 0, 0, 0}, {0, 1, 3, 7, 0, 0, 0, 0}, 
    {0, 1, 3, 6, 0, 0, 0, 0}, {0, 1, 3, 6, 7, 0, 0, 0}, 
    {0, 1, 3, 5, 0, 0, 0, 0}, {0, 1, 3, 5, 7, 0, 0, 0}, 
    {0, 1, 3, 5, 6, 0, 0, 0}, {0, 1, 3, 5, 6, 7, 0, 0}, 
    {0, 1, 3, 4, 0, 0, 0, 0}, {0, 1, 3, 4, 7, 0, 0, 0}, 
    {0, 1, 3, 4, 6, 0, 0, 0}, {0, 1, 3, 4, 6, 7, 0, 0}, 
    {0, 1, 3, 4, 5, 0, 0, 0}, {0, 1, 3, 4, 5, 7, 0, 0}, 
    {0, 1, 3, 4, 5, 6, 0, 0}, {0, 1, 3, 4, 5, 6, 7, 0}, 
    {0, 1, 2, 0, 0, 0, 0, 0}, {0, 1, 2, 7, 0, 0, 0, 0}, 
    {0, 1, 2, 6, 0, 0, 0, 0}, {0, 1, 2, 6, 7, 0, 0, 0}, 
    {0, 1, 2, 5, 0, 0, 0, 0}, {0, 1, 2, 5, 7, 0, 0, 0}, 
    {0, 1, 2, 5, 6, 0, 0, 0}, {0, 1, 2, 5, 6, 7, 0, 0}, 
    {0, 1, 2, 4, 0, 0, 0, 0}, {0, 1, 2, 4, 7, 0, 0, 0}, 
    {0, 1, 2, 4, 6, 0, 0, 0}, {0, 1, 2, 4, 6, 7, 0, 0}, 
    {0, 1, 2, 4, 5, 0, 0, 0}, {0, 1, 2, 4, 5, 7, 0, 0}, 
    {0, 1, 2, 4, 5, 6, 0, 0}, {0, 1, 2, 4, 5, 6, 7, 0}, 
    {0, 1, 2, 3, 0, 0, 0, 0}, {0, 1, 2, 3, 7, 0, 0, 0}, 
    {0, 1, 2, 3, 6, 0, 0, 0}, {0, 1, 2, 3, 6, 7, 0, 0}, 
    {0, 1, 2, 3, 5, 0, 0, 0}, {0, 1, 2, 3, 5, 7, 0, 0}, 
    {0, 1, 2, 3, 5, 6, 0, 0}, {0, 1, 2, 3, 5, 6, 7, 0}, 
    {0, 1, 2, 3, 4, 0, 0, 0}, {0, 1, 2, 3, 4, 7, 0, 0}, 
    {0, 1, 2, 3, 4, 6, 0, 0}, {0, 1, 2, 3, 4, 6, 7, 0}, 
    {0, 1, 2, 3, 4, 5, 0, 0}, {0, 1, 2, 3, 4, 5, 7, 0}, 
    {0, 1, 2, 3, 4, 5, 6, 0}, {0, 1, 2, 3, 4, 5, 6, 7}
};

// TBD - We can reimplement ProtoBitmask to used "unsigned int"
//       words instead of "unsigned char" for its "mask" array.
//       Instead of the BITLOCS[][] lookup, we can use the 
//       approach where the least signficant set bit for 'x' can
//       be determined with "leastSetBit = (x & -x);"
//
//       Here's code to set bits and get the next set bit for a given "index"
//       (Note index zero is the least significant bit of word[0] here)
//
//       void SetBit(unsigned int* mask, unsigned int index)                                 
//       {                                                                                   
//           const unsigned int BITS_PER_WORD = 8*sizeof(unsigned int);                      
//           const unsigned int BSHIFT = log2(BITS_PER_WORD);                                
//           const unsigned int BMASK = (BITS_PER_WORD - 1);                                 
//           mask[(index >> BSHIFT)] |= (0x00000001 << (index & BMASK));                     
//       }                                                                                   
//                                                                                           
//       // Returns index of next set bit >= index                                           
//       bool GetNextSetBit(unsigned int* mask, unsigned int maskWords, unsigned int &index) 
//       {                                                                                   
//           const unsigned int BONES = ((unsigned int)-1);  // all ones                     
//           const unsigned int BITS_PER_WORD = 8*sizeof(unsigned int);                      
//           const unsigned int BSHIFT = log2(BITS_PER_WORD);                                
//           const unsigned int BMASK = (BITS_PER_WORD - 1);                                 
//                                                                                           
//           unsigned int maskIndex = index >> BSHIFT;                                       
//           unsigned int word = mask[maskIndex];                                            
//           if (0 != word)                                                                  
//           {                                                                               
//               unsigned int bitIndex = index & BMASK;                                      
//               word &= BONES << bitIndex ;  // mask bits < bitIndex                        
//               if (0 != word)                                                              
//               {                                                                           
//                   unsigned int nextSet = (word & -word);                                  
//                   if (0 != nextSet)                                                       
//                   {                                                                       
//                       unsigned int bitOffset = 0;                                         
//                       while (0 != (nextSet >>= 1)) bitOffset++;                           
//                       index = (maskIndex << BSHIFT) + bitOffset;                          
//                       return true;                                                        
//                   }                                                                       
//               }                                                                           
//           }                                                                               
//           while (++maskIndex < maskWords)                                                 
//           {                                                                               
//               word = mask[maskIndex];                                                     
//               if (0 != word)                                                              
//               {                                                                           
//                   unsigned int nextSet = (word & -word);                                  
//                   if (0 != nextSet)                                                       
//                   {                                                                       
//                       unsigned int bitOffset = 0;                                         
//                       while (0 != (nextSet >>= 1)) bitOffset++;                           
//                       index = (maskIndex << BSHIFT) + bitOffset;                          
//                       return true;                                                        
//                   }                                                                       
//               }                                                                           
//           }                                                                               
//           return false;  // nothing was set                                               
//       }  // end GetNextSetBit()                                                           


ProtoBitmask::ProtoBitmask()
    : mask(NULL), mask_len(0), 
      num_bits(0), first_set(0)
{
}

ProtoBitmask::~ProtoBitmask()
{
    Destroy();
}

bool ProtoBitmask::Init(UINT32 numBits)
{
    if (mask) Destroy();
    // Allocate memory for mask
    unsigned int len = (numBits + 7) >> 3;
    if ((mask = new unsigned char[len]))
    {
        num_bits = numBits;
        mask_len = len;
        Clear();
        return true;
    }
    else
    {
        return false;
    }
   
}  // end ProtoBitmask::Init()

void ProtoBitmask::Destroy()
{
    if (mask) 
    {
        delete[] mask;
        mask = (unsigned char*)NULL;
        num_bits = first_set = 0;
    }
}  // end ProtoBitmask::Destroy()


bool ProtoBitmask::GetNextSet(UINT32& index) const
{   
    if (index >= num_bits) return false;
    if (index < first_set) return GetFirstSet(index);
    UINT32 maskIndex = index >> 3;
    if (mask[maskIndex])
    {
        int w = WEIGHT[mask[maskIndex]];
        int remainder = index & 0x07;
        for (int i = 0; i < w; i++)
        {
            int loc = BITLOCS[mask[maskIndex]][i];
            if (loc >= remainder) 
            {
                index = (maskIndex << 3) + loc;
                return true;
            }
        }
    }
    while(++maskIndex < mask_len)
    {
        if (mask[maskIndex])
        {
            index = (maskIndex << 3) +  BITLOCS[mask[maskIndex]][0];
            return true;
        }
    }
    return false;
}  // end ProtoBitmask::NextSet()

bool ProtoBitmask::GetPrevSet(UINT32& index) const
{
    if (index >= num_bits) index = num_bits - 1;
    if (index < first_set) return false;
    UINT32 maskIndex = index >> 3;
    if (mask[maskIndex])
    {
        int w = WEIGHT[mask[maskIndex]] - 1;
        int remainder = index & 0x07;
        for (int i = w; i >= 0; i--)
        {
            int loc = BITLOCS[mask[maskIndex]][i];
            if (loc <= remainder) 
            {
                index = ((maskIndex << 3) + loc);
                return true;
            }
        }
    }
    maskIndex--;
    UINT32 startIndex = first_set >> 3;
    for (; maskIndex >= startIndex; maskIndex--)
    {
        if (0 != mask[maskIndex])
        {
            int w = WEIGHT[mask[maskIndex]] - 1;
            index = ((maskIndex << 3) + BITLOCS[mask[maskIndex]][w]);
            return true;
        }
    }
    return false;  // (nothing prior was set)
}  // end ProtoBitmask::GetPrevSet()

bool ProtoBitmask::GetNextUnset(UINT32& index) const
{
    if (index >= num_bits) return false;
    UINT32 next = index;
    UINT32 maskIndex = next >> 3;
    unsigned char bit = 0x80 >> (next & 0x07);
    while (next < num_bits)
    {
        unsigned char val = mask[maskIndex];
        if (val)
        {
            while (bit && (next < num_bits))
            {
                if (0 == (val & bit)) 
                {
                    index = next;
                    return true;
                }
                next++;   
                bit >>= 0x01;
            }
            bit = 0x80;
            maskIndex++;
        }
        else
        {
            index = next;
            return true;
        }
    }
    return false;
}  // end ProtoBitmask::GetNextUnset()


bool ProtoBitmask::SetBits(UINT32 index, UINT32 count)
{
    if (0 == count) return true;
    if ((index+count) > num_bits) return false;
    UINT32 maskIndex = index >> 3;
    // To set appropriate bits in first byte
    unsigned int bitIndex = index & 0x07;
    unsigned int bitRemainder = 8 - bitIndex;
    if (count <= bitRemainder)
    {
        mask[maskIndex] |= (0x00ff >> bitIndex) &
                           (0x00ff << (bitRemainder - count)); 
    }
    else
    {
        mask[maskIndex] |= 0x00ff >> bitIndex;
        count -= bitRemainder;
        INT32 nbytes = count >> 3;  
        memset(&mask[++maskIndex], 0xff, nbytes);
        count &= 0x07;  
        if (count)
            mask[maskIndex+nbytes] |= 0xff << (8-count);
    }
    if (index < first_set) first_set = index;
    return true;
}  // end ProtoBitmask::SetBits()


bool ProtoBitmask::UnsetBits(UINT32 index, UINT32 count)
{
    if ((index >= num_bits)|| (0 == count)) return true;
    UINT32 end = index + count;
    if (end > num_bits) 
    {
        end = num_bits;
        count = end - index;
    }
    UINT32 maskIndex = index >> 3;
    // To unset appropriate bits in first byte
    unsigned int bitIndex = index & 0x07;
    unsigned int bitRemainder = 8 - bitIndex;
    if (count <= bitRemainder)
    {
        mask[maskIndex] &= (0x00ff << bitRemainder) |
                           (0x00ff >> (bitIndex + count)); 
    }
    else
    {
        mask[maskIndex] &= 0x00ff << bitRemainder;
        count -= bitRemainder;
        INT32 nbytes = count >> 3;  
        memset(&mask[++maskIndex], 0, nbytes);
        count &= 0x07;  
        if (count) mask[maskIndex+nbytes] &= 0xff >> count;
    }
    if ((first_set >= index) && (end > first_set))
    { 
        first_set = end;
        if (!GetNextSet(first_set)) first_set = num_bits;
    }
    return true;
}  // end ProtoBitmask::UnsetBits()

// this = b
bool ProtoBitmask::Copy(const ProtoBitmask &b)
{
    if (b.num_bits > num_bits) return false;
    memcpy(mask, b.mask, b.mask_len);
    (mask_len > b.mask_len) ? 
        memset(mask+b.mask_len, 0, mask_len - b.mask_len) : 0;
    first_set = (b.first_set < b.num_bits) ? b.first_set : num_bits;
    return true;
}  // end ProtoBitmask::Copy()

// this = this | b
bool ProtoBitmask::Add(const ProtoBitmask& b)
{
    if (b.num_bits > num_bits) return false;   
    for(unsigned int i = 0; i < b.mask_len; i++)
        mask[i] |= b.mask[i];
    if ((b.first_set < first_set) &&
        (b.first_set < b.num_bits))
        first_set = b.first_set;
    return true;
}  // end ProtoBitmask::Add()

// this = this & ~b
bool ProtoBitmask::Subtract(const ProtoBitmask& b)
{
    UINT32 len = (mask_len < b.mask_len) ? mask_len : b.mask_len;
    for(UINT32 i = 0; i < len; i++)
        mask[i] &= ~b.mask[i];
    if (first_set >= b.first_set) 
    {
        if (!GetNextSet(first_set)) first_set = num_bits;
    }
    return true;
}  // end ProtoBitmask::Subtract()


// this = ~this & b  (this = b - this)
bool ProtoBitmask::XCopy(const ProtoBitmask& b)
{
    if (b.num_bits > num_bits) return false;
    unsigned int len = b.mask_len;
    unsigned int begin = b.first_set >> 3;
    if (begin) memset(mask, 0, begin);
    for (unsigned int i = begin; i < len; i++)
        mask[i] = b.mask[i] & ~mask[i];
    if (len < mask_len) memset(&mask[len], 0, mask_len - len);
    UINT32 theFirst = (b.first_set < b.num_bits) ? b.first_set : num_bits;
    if (theFirst < first_set)
    {
        first_set = b.first_set;
    }
    else
    {
        first_set = theFirst;
        if (!GetNextSet(first_set)) first_set = num_bits;
    }
    return true;
}  // end ProtoBitmask::XCopy()

// this = this & b
bool ProtoBitmask::Multiply(const ProtoBitmask& b)
{
    UINT32 len = (mask_len < b.mask_len) ? mask_len : b.mask_len;   
    for(unsigned int i = 0; i < len; i++)
        mask[i] |= b.mask[i];
    if (len < mask_len) memset(&mask[len], 0, mask_len - len);
    
    if (b.first_set > first_set)
    {
        first_set = b.first_set;
        if (!GetNextSet(first_set)) first_set = num_bits;
    }
    else if (first_set > b.first_set)
    {
        if (!GetNextSet(first_set)) first_set = num_bits;
    }
    return true;
}  // end ProtoBitmask::Multiply()

// this = this ^ b
bool ProtoBitmask::Xor(const ProtoBitmask& b)
{
    // Does "b" have any bits set?
    if (!b.IsSet()) return true; 
    if (b.num_bits > num_bits) return false;
    for(unsigned int i = 0; i < b.mask_len; i++)
        mask[i] ^= b.mask[i];
    if (b.first_set == first_set)
    {
        if (!GetNextSet(first_set)) first_set = num_bits;
    }
    else if (b.first_set < first_set)
    {
        first_set = b.first_set;
    }
    return true;
}  // end ProtoBitmask::Xor()

void ProtoBitmask::Display(FILE* stream)
{
    UINT32 index = 0;
    for (UINT32 i = 0; i < num_bits; i++)
    {
        if (Test(index++)) fprintf(stream, "1"); else fprintf(stream, "0");
        if (0x07 == (i & 0x07)) fprintf(stream, " ");
        if (0x3f == (i & 0x3f)) fprintf(stream, "\n");
    }
}  // end ProtoBitmask::Display()


ProtoSlidingMask::ProtoSlidingMask()
 : mask((unsigned char*)NULL), mask_len(0), num_bits(0), 
   start(0), end(0), offset(0)
{
}


ProtoSlidingMask::~ProtoSlidingMask()
{
    Destroy();
}

bool ProtoSlidingMask::Init(INT32 numBits, UINT32 rangeMask)
{
    if (mask) Destroy();
    
    //TRACE("ProtoSlidingMask::Init() rangeMask>%lu (0x%0x)\n", rangeMask, rangeMask);
    
    if ((numBits <= 0) || ((UINT32)numBits > ((rangeMask>>1)+1))) 
        return false;
    UINT32 len = (numBits + 7) >> 3;
    if ((mask = new unsigned char[len]))
    {
        range_mask = rangeMask;
        range_sign = (rangeMask ^ (rangeMask >> 1));
        mask_len = len;
        num_bits = numBits;
        Clear();
        return true;
    }
    else
    {
        return false;
    }
}  // end ProtoSlidingMask::Init()

bool ProtoSlidingMask::Resize(INT32 numBits)
{
    // 1) Backup the current state
    ProtoSlidingMask tempMask = *this;
    // 2) Prune if needed.
    if (numBits < num_bits)
        tempMask.UnsetBits(offset+numBits, num_bits-numBits); 
    // 3) Re-init w/ new "numBits"
    mask = NULL;
    bool result =  Init(numBits, range_mask);
    if (result)
    {
        // 4) Copy old mask content
        result = Copy(tempMask);
        ASSERT(result);
    }
    else
    {
        *this = tempMask;
        tempMask.mask = NULL;
    }
    tempMask.Destroy();
    return result;
}  // end ProtoSlidingMask::Resize()

void ProtoSlidingMask::Destroy()
{
    if (mask)
    {
        delete[] mask;
        mask = NULL;
        mask_len = num_bits = start = end = offset = 0;
    }   
}  // end ProtoSlidingMask::Destroy()

bool ProtoSlidingMask::CanSet(UINT32 index) const
{
    if (IsSet())
    {
        // Determine position with respect to current start
        // and end, given the "offset" of the current start  
        INT32 pos = Delta(index, offset);
        if (pos < 0)
        {
            // Precedes start.
            pos += start;
            if (pos < 0) pos += num_bits;
            if (pos < 0)
            {
                // out of range
                return false;
            }
            else
            {
                // Is pos between end & start?
                if (end < start)
                {
                   if ((pos <= end) || (pos >= start)) return false; 
                }
                else
                {
                   if ((pos <= end) && (pos >= start)) return false;
                }
                return true;
            } 
        }
        else if (pos < num_bits)
        {
                return true;
        }
        else
        {
                return false;  // out of range
        }
    }
    else
    {
        return true;  // empty mask can be set in any fashion
    }
}  // end ProtoSlidingMask::CanSet()

bool ProtoSlidingMask::Set(UINT32 index)
{
    if (IsSet())
    {        
        // Determine position with respect to current start
        // and end, given the "offset" of the current start               
        INT32 pos = Delta(index, offset);  
        if (pos < 0)
        {
            // Precedes start.
            pos += start;
            if (pos < 0) pos += num_bits;
            if (pos < 0)
            {
                // out of range
                return false;
            }
            else
            {
                // Is pos between end & start?
                if (end < start)
                {
                   if ((pos <= end) || (pos >= start)) return false; // Brian fix 14 Mar 2011 >= start
                }
                else
                {
                    if ((pos <= end) && (pos >= start)) return false;  // Brian fix 17 JUL 2007 >= start
                }
                // Ok for new "start" && "offset"
                start = pos;
                offset = index;
            } 
        }
        else if (pos < num_bits)
        {
            pos += start;
            if (pos >= num_bits) pos -= num_bits;
            if (end < start)
            {
                if ((pos < start) && (pos > end)) end = pos;  
            }
            else
            {
                if ((pos > end) || (pos < start)) end = pos;
            }
        }
        else
        {
            return false;  // out of range
        }
        ASSERT((pos >> 3) >= 0);
        ASSERT((pos >> 3) < (INT32)mask_len);
        mask[(pos >> 3)] |= (0x80 >> (pos & 0x07));
    }
    else
    {
        start = end = 0;
        offset = index;   
        mask[0] = 0x80;
    }
    return true;
}  // end ProtoSlidingMask::Set()

bool ProtoSlidingMask::Unset(UINT32 index)
{
    //ASSERT(CanSet(index));
    if (IsSet())
    {
        INT32 pos = Delta(index, offset);
        if (pos < 0)
        {
            return true;  // out-of-range
        }
        else if (pos < num_bits)
        {
            // Is it in current range of set bits?
            pos += start;
            if (pos >= num_bits) pos -= num_bits;
            if (end < start)
            {
                if ((pos > end) && (pos < start)) return true;   
            }
            else
            {
                if ((pos < start) || (pos > end)) return true;   
            }
            // Yes, it was in range.
            // Unset the corresponding bit
            ASSERT((pos >> 3) >= 0);
            ASSERT((pos >> 3) < (INT32)mask_len);
            mask[(pos >> 3)] &= ~(0x80 >> (pos & 0x07));
            if (start == end) 
            {
                ASSERT(pos == start);
                start = end = num_bits;
                return true;
            }
            if (start == pos) 
            {
                UINT32 next = index;
                if (!GetNextSet(next)) 
                    ASSERT(0);
                INT32 delta = Delta(next, offset);
                ASSERT(delta >= 0);
                start += delta;
                if (start >= num_bits) start -= num_bits;
                offset = next;
            }
            if (pos == end) 
            {
                UINT32 prev = index;
                if (!GetPrevSet(prev)) 
                    ASSERT(0);
                INT32 delta = Delta(prev, offset);
                ASSERT(delta >= 0);
                end = start + delta;
                if (end >= num_bits) end -= num_bits;
            }
        }
        else
        {
            return true; // out-of-range   
        }
    }
    return true;
}  // end ProtoSlidingMask::Unset()

bool ProtoSlidingMask::SetBits(UINT32 index, INT32 count)
{
    if (count < 0) return false;
    if (0 == count) return true;
    INT32 firstPos, lastPos;
    if (IsSet())
    {
        INT32 last = (index + count - 1) & range_mask;
        if (!CanSet(index)) return false;
        if (!CanSet(last)) return false; 
        // Calculate first set bit position  
        firstPos = Delta(index, offset);
        if (firstPos < 0)
        {
            // precedes start
            firstPos += start;
            if (firstPos < 0) firstPos += num_bits;
            start = firstPos;
            offset = index;
        }
        else
        {
            firstPos += start;
            if (firstPos >= num_bits) firstPos -= num_bits;
        }
        // Calculate last set bit position
        lastPos = Delta(last , offset);
        if (lastPos > 0)
        {
            // Is post start, post end?  
            lastPos += start; 
            if (lastPos >= num_bits) lastPos -= num_bits;
            if (end < start)
            {
                if ((lastPos < start) && (lastPos > end)) end = lastPos;  
            }
            else
            {
                if ((lastPos > end) || (lastPos < start)) end = lastPos;
            }
        }
        else
        {
            lastPos += start;
            if (lastPos < 0) lastPos += num_bits;
        }
        if (lastPos < firstPos)
        {
            // Set bits from firstPos to num_bits   
            count = num_bits - firstPos;
            INT32 maskIndex = firstPos >> 3;
            int bitIndex = firstPos & 0x07;
            int bitRemainder = 8 - bitIndex;
            ASSERT(maskIndex >= 0);
            if (count <= bitRemainder)
            {
                ASSERT(maskIndex < (INT32)mask_len);
                mask[maskIndex] |= (0x00ff >> bitIndex) &
                                   (0x00ff << (bitRemainder - count)); 
            }
            else
            {
                ASSERT(maskIndex < (INT32)mask_len);
                mask[maskIndex] |= 0x00ff >> bitIndex;
                count -= bitRemainder;
                INT32 nbytes = count >> 3;  
                ASSERT((maskIndex+1+nbytes) <= (INT32)mask_len);
                memset(&mask[++maskIndex], 0xff, nbytes);
                count &= 0x07;  
                if (count) 
                {
                    ASSERT((maskIndex+nbytes) >= 0);
                    ASSERT((maskIndex+nbytes) < (INT32)mask_len);
                    mask[maskIndex+nbytes] |= 0xff << (8-count);
                }
            }
            firstPos = 0;
        }
    }
    else
    {
        if (count > num_bits) return false;
        start = firstPos = 0;
        end = lastPos = (INT32)(count - 1);
        offset = index;
    }
    // Set bits from firstPos to lastPos   
    count = lastPos - firstPos + 1;
    INT32 maskIndex = firstPos >> 3;
    int bitIndex = firstPos & 0x07;
    int bitRemainder = 8 - bitIndex;
    ASSERT(maskIndex >= 0);
    if (count <= bitRemainder)
    {
        ASSERT(maskIndex < (INT32)mask_len);
        mask[maskIndex] |= (0x00ff >> bitIndex) &
                            (0x00ff << (bitRemainder - count)); 
    }
    else
    {
        ASSERT(maskIndex < (INT32)mask_len);
        mask[maskIndex] |= 0x00ff >> bitIndex;
        count -= bitRemainder;
        INT32 nbytes = count >> 3;
        ASSERT((maskIndex+1+nbytes) <= (INT32)mask_len);  
        memset(&mask[++maskIndex], 0xff, nbytes);
        count &= 0x07;  
        if (count) 
        {
            ASSERT((maskIndex+nbytes) >= 0);
            ASSERT((maskIndex+nbytes) < (INT32)mask_len);
            mask[maskIndex+nbytes] |= 0xff << (8-count);
        }
    }
    return true;
}  // end ProtoSlidingMask::SetBits()

bool ProtoSlidingMask::UnsetBits(UINT32 index, INT32 count)
{
    if (IsSet())
    {
        // Trim to fit as needed.
        INT32 firstPos;
        if (count <= 0) return true;
        if (count > num_bits) count = num_bits;
        INT32 delta = Delta(index, offset);
        if (delta >= num_bits)
        {
            return true;
        }
        else if (delta <= 0)
        {
            firstPos = start;  
            count += delta; 
            if (count <= 0) return true;
        }
        else
        {
            firstPos = start + delta;
            if (firstPos >= num_bits) firstPos -= num_bits;
        }
        UINT32 lastSet;
        if (!GetLastSet(lastSet)) 
            ASSERT(0);
        delta = Delta(((index+count-1) & range_mask), lastSet);
        INT32 lastPos;
        if (delta < 0)
        { 
            lastPos = firstPos + count - 1;
            if (lastPos >= num_bits) lastPos -= num_bits;
        }
        else
        {
            lastPos = end;
        }
        INT32 startPos;
        if (lastPos < firstPos)
        {
            // Clear bits from firstPos to num_bits   
            count = num_bits - firstPos;
            INT32 maskIndex = firstPos >> 3;
            int bitIndex = firstPos & 0x07;
            int bitRemainder = 8 - bitIndex;
            if (count <= bitRemainder)
            {
                ASSERT(maskIndex < (INT32)mask_len);
                mask[maskIndex] &= (0x00ff << bitRemainder) |
                                   (0x00ff >> (bitIndex + count));
            }
            else
            {
                ASSERT(maskIndex < mask_len);
                mask[maskIndex] &= 0x00ff << bitRemainder;
                count -= bitRemainder;
                INT32 nbytes = count >> 3;  
                ASSERT((maskIndex+1+nbytes) <= mask_len);
                memset(&mask[++maskIndex], 0, nbytes);
                count &= 0x07;  
                if (count) 
                {
                    ASSERT((maskIndex+nbytes) < mask_len);
                    mask[maskIndex+nbytes] &= 0xff >> count;
                }
            }
            startPos = 0;
        }
        else
        {
            startPos = firstPos;
        }
        // Unset bits from firstPos to lastPos   
        count = lastPos - startPos + 1;
        INT32 maskIndex = startPos >> 3;
        int bitIndex = startPos & 0x07;
        int bitRemainder = 8 - bitIndex;
        if (count <= bitRemainder)
        {
            ASSERT(maskIndex < mask_len);
            mask[maskIndex] &= (0x00ff << bitRemainder) |
                               (0x00ff >> (bitIndex + count)); 
        }
        else
        {
            ASSERT(maskIndex < mask_len);
            mask[maskIndex] &= 0x00ff << bitRemainder;
            count -= bitRemainder;
            INT32 nbytes = count >> 3;
            ASSERT((maskIndex+1+nbytes) <= mask_len);
            memset(&mask[++maskIndex], 0, nbytes);
            count &= 0x07;  
            if (count) 
            {   
                ASSERT((maskIndex+nbytes) < mask_len);
                mask[maskIndex+nbytes] &= 0xff >> count;
            }
        }
        // Calling these will properly update the offset/start/end state
        if (start == firstPos) 
        {
            if (end == lastPos)
            {
                start = end = num_bits;
            }
            else
            {
                Unset(offset);
            }
        }
        else if (end == lastPos) 
        {
            UINT32 lastSet;
            GetLastSet(lastSet);
            Unset(lastSet);
        }
    }
    return true;
}  // end ProtoSlidingMask::UnsetBits()

bool ProtoSlidingMask::Test(UINT32 index) const
{
    if (IsSet())
    {
        INT32 pos = Delta(index , offset);
        if (pos >= 0)
        {
            // Is it in range?
            if (pos >= num_bits) return false;
            pos += start;
            if (pos >= num_bits) pos -= num_bits;
            if (end < start)
            {
                if ((pos > end) && (pos < start)) return false;   
            }
            else
            {
                if ((pos < start) || (pos > end)) return false;   
            }
            // Test the corresponding bit
            if (0 != (mask[(pos >> 3)] & (0x80 >> (pos & 0x07))))
                return true;
        }
    }
    return false;
}  // end ProtoSlidingMask::Test()


bool ProtoSlidingMask::GetNextSet(UINT32& index) const
{
    if (IsSet())
    {
        UINT32 next = index;
        INT32 pos = Delta(next, offset);
        if (pos >= 0)
        {
            // Is it in range?
            if (pos >= num_bits) return false;
            pos += start;
            if (pos >= num_bits) pos -= num_bits;
            
            if (end < start)
            {
                if ((pos > end) && (pos < start)) return false;
            }
            else
            {
                if ((pos < start) || (pos > end)) return false;
            }
            // Seek next set bit
            INT32 maskIndex = pos >> 3;
            if (mask[maskIndex])
            {
                int w = ProtoBitmask::WEIGHT[mask[maskIndex]];
                int remainder = pos & 0x07;
                for (int i = 0; i < w; i++)
                {
                    int loc = ProtoBitmask::BITLOCS[mask[maskIndex]][i];
                    if (loc >= remainder) 
                    {
                        pos = (maskIndex << 3) + loc;
                        pos -= start;
                        if (pos < 0) pos += num_bits;
                        index = offset + pos;
                        index &= range_mask;
                        return true;
                    }
                }
            }
            maskIndex++;
            if (end < pos)
            {
                for (; maskIndex < mask_len; maskIndex++)
                {
                    if (mask[maskIndex])
                    {
                        pos = (maskIndex << 3) + ProtoBitmask::BITLOCS[mask[maskIndex]][0];
                        pos -= start;
                        if (pos < 0) pos += num_bits;
                        index =  offset + pos;
                        index &= range_mask;
                        return true;
                    }
                }
                maskIndex = 0;
            }
            INT32 endIndex = end >> 3;
            for (; maskIndex <= endIndex; maskIndex++)
            {
                if (mask[maskIndex])
                {
                    pos = (maskIndex << 3) + ProtoBitmask::BITLOCS[mask[maskIndex]][0];
                    pos -= start;
                    if (pos < 0) pos += num_bits;
                    index = offset + pos;
                    index &= range_mask;
                    return true;
                }
            }
        }
        else
        {
            index = offset;
            return true;
        }  // end if/else (pos >= 0)
    }
    return false;  // indicates nothing was set
}  // end ProtoSlidingMask::GetNextSet()

bool ProtoSlidingMask::GetPrevSet(UINT32& index) const
{
    if (IsSet())
    {
        UINT32 prev = index;
        INT32 pos = Delta(prev, offset);
        if (pos >= 0)
        {
            // Is it in range?
            if (pos >= num_bits) 
            {
                GetLastSet(index);
                return true;
            }
            pos += start;
            if (pos >= num_bits) pos -= num_bits;
            if (end < start)
            {
                if ((pos > end) && (pos < start)) 
                {
                    GetLastSet(index);
                    return true;
                }
            }
            else
            {
                if ((pos < start) || (pos > end)) 
                {
                    GetLastSet(index);
                    return true;
                }
            }
            // Seek prev set bits, starting with index   
            INT32 maskIndex = pos >> 3;
            if (mask[maskIndex])
            {
                int w = ProtoBitmask::WEIGHT[mask[maskIndex]] - 1;
                int remainder = pos & 0x07;
                for (int i = w; i >= 0; i--)
                {
                    int loc = ProtoBitmask::BITLOCS[mask[maskIndex]][i];
                    if (loc <= remainder) 
                    {
                        pos = (maskIndex << 3) + loc;
                        pos -= start;
                        if (pos < 0) pos += num_bits;
                        index = offset + pos;
                        index &= range_mask;
                        return true;
                    }
                }
            }
            maskIndex--;
            if (pos < start) 
            {
                for(; maskIndex >= 0; maskIndex--)
                {                   
                    if (mask[maskIndex])
                    {
                        
                        int w = ProtoBitmask::WEIGHT[mask[maskIndex]] - 1;
                        pos =  (maskIndex << 3) + ProtoBitmask::BITLOCS[mask[maskIndex]][w];
                        pos -= start;
                        if (pos < 0) pos += num_bits;
                        index = offset + pos;
                        index &= range_mask;
                        return true;  
                    }
                } 
                maskIndex = mask_len - 1;  
            }
            INT32 startIndex = start >> 3;
            for (; maskIndex >= startIndex; maskIndex--)
            {
                if (mask[maskIndex])
                {
                    int w = ProtoBitmask::WEIGHT[mask[maskIndex]] - 1;
                    pos =  (maskIndex << 3) + ProtoBitmask::BITLOCS[mask[maskIndex]][w];
                    pos -= start;
                    if (pos < 0) pos += num_bits;
                    index = offset + pos;
                    index &= range_mask;
                    return true;  
                }
            }
        }
    }
    return false;  // indicates nothing prior was set
}  // end ProtoSlidingMask::GetPrevSet()

bool ProtoSlidingMask::Copy(const ProtoSlidingMask& b)
{
    if (b.IsSet())
    {
        INT32 range = b.end - b.start;
        if (range < 0) range += b.num_bits;
        if (range <= num_bits)
        {
            start = b.start & 0x07;
            UINT32 bLastSet;
            b.GetLastSet(bLastSet);
            UINT32 bFirstSet;
            b.GetFirstSet(bFirstSet);
            end = bLastSet - bFirstSet + start;
            offset = b.offset;
            // Copy start to mask_len
            INT32 startIndex = b.start >> 3;
            INT32 endIndex = b.end >> 3;
            if (b.end < b.start)
            {
                ASSERT((b.mask_len - startIndex) <= mask_len);
                memcpy(mask, b.mask+startIndex, b.mask_len - startIndex);
                ASSERT((b.mask_len - startIndex + endIndex) <= mask_len);
                //memcpy(mask+b.mask_len-startIndex, b.mask, endIndex+1);  // old
                memcpy(mask+b.mask_len-startIndex, b.mask, endIndex);    // new
                // Clear any possible start/end overlap
                if (mask_len > b.mask_len)
                {
                    unsigned int remainder = start & 0x07;
                    if (remainder) mask[0] &= 0xff >> remainder;
                    remainder = end & 0x7;
                    if (remainder) 
                    {
                        ASSERT((startIndex+endIndex) < mask_len);
                        mask[startIndex+endIndex] &= 0xff << (8 - remainder);
                    }
                }            
            }
            else
            {
                ASSERT((endIndex-startIndex+1) <= mask_len);
                memcpy(mask, b.mask+startIndex, endIndex-startIndex+1);
            }        
            return true;
        }
        else
        {
            return false;
        }
    }
    else
    {
        Clear();
        return true;
    }
}  // end ProtoSlidingMask::Copy()

// Logically OR two bit mask such that "this = (this | b)"
bool ProtoSlidingMask::Add(const ProtoSlidingMask& b)
{
    if (b.IsSet())
    {
        if (IsSet())
        {
            UINT32 bFirstSet;
            b.GetFirstSet(bFirstSet);
            if (!CanSet(bFirstSet)) return false;
            UINT32 bLastSet;
            b.GetFirstSet(bLastSet);
            if (!CanSet(bLastSet)) return false;
            INT32 range = b.end - b.start;
            if (range < 0) range += b.num_bits;
            UINT32 index;
            b.GetFirstSet(index);
            for (INT32 i = 0; i < range; i++)
            {
                // (TBD) Improve performance by getting/setting
                //       ranges of set bits.
                if (b.Test(index)) Set(index);
                index++; 
            }
            return true;
        }
        else
        {
            return Copy(b);
        }
    }
    return true;
}  // end ProtoSlidingMask::Add()

// A sort of logical subtraction "this = (this & ~b)"
// This leaves us with bits uniquely set in "this" 
bool ProtoSlidingMask::Subtract(const ProtoSlidingMask& b)
{
    if (b.IsSet())
    {
        if (IsSet())
        {
            UINT32 index = offset;
            INT32 range = end - start;
            if (range < 0) range += num_bits;
            for (INT32 i = 0; i < range; i++)
            {
                if (Test(index) && b.Test(index)) Unset(index);
                index++;   
            }
        } 
    }
    return true;
}  // end ProtoSlidingMask::Subtract()

// A sort of logical subtraction "this = (~this & b)"
// This leaves us with bits uniquely set in "b"
bool ProtoSlidingMask::XCopy(const ProtoSlidingMask& b)
{
    if (b.IsSet())
    {
        if (IsSet())
        {
            UINT32 bFirstSet;
            b.GetFirstSet(bFirstSet);
            if (!CanSet(bFirstSet)) return false;
            UINT32 bLastSet;
            b.GetFirstSet(bLastSet);
            if (!CanSet(bLastSet)) return false;
            UINT32 index;
            b.GetFirstSet(index);
            INT32 range = b.end - b.start;
            if (range < 0) range += b.num_bits;
            for (INT32 i = 0; i < range; i++)
            {
                if (Test(index))
                    Unset(index);
                else if (b.Test(index))
                    Set(index);
                index++;   
            }
        }
        else
        {
            return Copy(b);   
        } 
    }
    else
    {
        Clear();
    }
    return true;
}  // end ProtoSlidingMask::XCopy()

// Logically AND two bit mask such that "this = (this & b)"
bool ProtoSlidingMask::Multiply(const ProtoSlidingMask& b)
{
    if (b.IsSet())
    {
        if (IsSet())
        {
            UINT32 index = offset;
            INT32 range = end - start;
            if (range < 0) range += num_bits;
            for (INT32 i = 0; i < range; i++)
            {
                if (Test(index) && !b.Test(index)) Unset(index);
                index++;   
            }
        } 
    }
    else
    {
        Clear();
    }
    return true;
}  // end ProtoSlidingMask::Multiply()

// Logically XOR two bit mask such that "this = (this ^ b)"
// (TBD) rewrite for byte-based operation for better efficiency
bool ProtoSlidingMask::Xor(const ProtoSlidingMask& b)
{
    if (b.IsSet())
    {
        UINT32 bFirstSet;
        b.GetFirstSet(bFirstSet);
        if (!CanSet(bFirstSet)) return false;
        UINT32 bLastSet;
        b.GetFirstSet(bLastSet);
        if (!CanSet(bLastSet)) return false;
        UINT32 index;
        b.GetFirstSet(index);
        INT32 range = b.end - b.start;
        if (range < 0) range += b.num_bits;
        for (INT32 i = 0; i < range; i++)
        {
            if (b.Test(index)) Invert(index);
            index++;   
        }
    }
    return true;
}  // end ProtoSlidingMask::Xor()

void ProtoSlidingMask::Display(FILE* stream)
{
    UINT32 index = offset;
    for (INT32 i = 0; i < num_bits; i++)
    {
        if (Test(index++)) fprintf(stream, "1"); else fprintf(stream, "0");
        if (0x07 == (i & 0x07)) fprintf(stream, " ");
        if (0x3f == (i & 0x3f)) fprintf(stream, "\n");
    }
}  // end ProtoSlidingMask::Display()

void ProtoSlidingMask::Debug(INT32 theCount)
{
    UINT32 index = offset;
    theCount = MIN(theCount, num_bits);
    PLOG(PL_ERROR, "ProtoSlidingMask::Debug() offset:%lu\n   ", index);
    INT32 i;
    for (i = 0; i < theCount; i++)
    {
        if (Test(index++)) PLOG(PL_ERROR, "1"); else PLOG(PL_ERROR, "0");
        if (0x07 == (i & 0x07)) PLOG(PL_ERROR, " ");
        if (0x3f == (i & 0x3f)) PLOG(PL_ERROR, "\n   ");
    }
    if (0x3f != (i & 0x3f)) PLOG(PL_ERROR, "\n");
}  // end ProtoSlidingMask::Debug()
